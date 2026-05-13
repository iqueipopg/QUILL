import yaml, json, re, os, time
from agents.logger import get_logger


class BaseAgent:
    """Base class for all feedback agents. Supports local and API backends."""

    def __init__(self, agent_name):
        try:
            with open("config.yaml") as _f:
                self.config = yaml.safe_load(_f) or {}
        except FileNotFoundError:
            raise FileNotFoundError("config.yaml not found — run from project root directory")

        self.agent_name = agent_name
        self.logger = get_logger(self.__class__.__name__)
        self.backend = self.config.get("backend", "local")

        # Local backend needs model paths
        if self.backend == "local":
            if agent_name not in self.config.get("models", {}):
                raise KeyError(f"Model key '{agent_name}' not found in config.yaml 'models' section")
            self.model_path = self.config["models"][agent_name]
            self.device = self.config.get("device", "cuda")
            self.quantization = self.config.get("quantization", "none")
            gen_cfg = self.config.get("generation", {})
            self.do_sample = gen_cfg.get("do_sample", True)
            self.top_p = gen_cfg.get("top_p", 0.9)
            self.repetition_penalty = gen_cfg.get("repetition_penalty", 1.3)
        elif self.backend == "gemini":
            gemini_cfg = self.config.get("gemini", {})
            self._gemini_model = gemini_cfg.get("model", "gemini-2.0-flash")
            key_env = gemini_cfg.get("api_key_env", "GEMINI_API_KEY")
            self._gemini_key = os.environ.get(key_env)
            if not self._gemini_key:
                raise ValueError(
                    f"Gemini API key not found. Set the {key_env} environment variable.\n"
                    f"  Get a free key at: https://aistudio.google.com/apikey"
                )
        elif self.backend == "groq":
            groq_cfg = self.config.get("groq", {})
            self._groq_model = groq_cfg.get("model", "llama-3.3-70b-versatile")
            key_env = groq_cfg.get("api_key_env", "GROQ_API_KEY")
            self._groq_key = os.environ.get(key_env)
            if not self._groq_key:
                raise ValueError(
                    f"Groq API key not found. Set the {key_env} environment variable.\n"
                    f"  Get a free key at: https://console.groq.com"
                )
        else:
            raise ValueError(f"Unknown backend '{self.backend}'. Use 'local', 'gemini', or 'groq'.")

        self.model = None
        self.tokenizer = None
        self._loaded_path = None
        self._has_chat_template = None

    # ── Model loading ────────────────────────────────────────────

    def load_model(self, model_path=None):
        if self.backend != "local":
            self._loaded_path = self.backend
            return

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

        path = model_path or self.model_path
        if self._loaded_path == path and self.model is not None:
            return
        if self.model is not None:
            self.free_vram()
        self.logger.info("Loading %s from %s ...", self.agent_name, path)

        quant_config = None
        if self.quantization == "4bit":
            quant_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_use_double_quant=True,
                bnb_4bit_quant_type="nf4",
            )
        elif self.quantization == "8bit":
            quant_config = BitsAndBytesConfig(load_in_8bit=True)

        self.tokenizer = AutoTokenizer.from_pretrained(path, trust_remote_code=True)
        self.model = AutoModelForCausalLM.from_pretrained(
            path,
            quantization_config=quant_config,
            device_map=self.device,
            trust_remote_code=True,
            torch_dtype=torch.float16,
        )

        self._has_chat_template = (
            hasattr(self.tokenizer, "chat_template")
            and self.tokenizer.chat_template is not None
        )
        self._loaded_path = path
        self.logger.info("%s loaded on %s", self.agent_name, self.device)

    def free_vram(self):
        if self.backend != "local":
            return
        import torch, gc
        if self.model is not None:
            del self.model
            self.model = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        self._loaded_path = None
        self._has_chat_template = None
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()

    # ── Generation ───────────────────────────────────────────────

    def generate(self, prompt, max_new_tokens=512, temperature=0.7, system_prompt=None):
        """Generate text from the model, dispatching to the configured backend."""
        if self.backend == "gemini":
            return self._generate_gemini(prompt, max_new_tokens, temperature, system_prompt)
        if self.backend == "groq":
            return self._generate_groq(prompt, max_new_tokens, temperature, system_prompt)
        return self._generate_local(prompt, max_new_tokens, temperature, system_prompt)

    # Track last API call time to enforce minimum delay between calls
    _last_api_call = 0.0

    def _generate_gemini(self, prompt, max_new_tokens, temperature, system_prompt):
        """Call the Gemini REST API."""
        import requests

        # Enforce minimum delay between API calls (respects free tier RPM)
        min_delay = self.config.get("gemini", {}).get("min_delay_s", 4)
        elapsed = time.time() - BaseAgent._last_api_call
        if elapsed < min_delay:
            time.sleep(min_delay - elapsed)

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"models/{self._gemini_model}:generateContent?key={self._gemini_key}"
        )

        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_new_tokens,
            },
        }
        if system_prompt:
            body["systemInstruction"] = {"parts": [{"text": system_prompt}]}

        for attempt in range(5):
            BaseAgent._last_api_call = time.time()
            resp = requests.post(url, json=body, timeout=120)
            if resp.status_code in (429, 503):
                wait = 2 ** attempt * 5
                self.logger.warning("Gemini %d, waiting %ds...", resp.status_code, wait)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                self.logger.error("Gemini API error %d: %s", resp.status_code, resp.text[:300])
                raise RuntimeError(f"Gemini API returned {resp.status_code}")
            break
        else:
            raise RuntimeError("Gemini API rate limit exceeded after 5 retries")

        data = resp.json()
        try:
            # Gemini 2.5 may return multiple parts (thinking + response); take the last one
            parts = data["candidates"][0]["content"]["parts"]
            text = parts[-1]["text"].strip()
            return text
        except (KeyError, IndexError):
            self.logger.error("Unexpected Gemini response: %s", json.dumps(data)[:300])
            return ""

    def _generate_groq(self, prompt, max_new_tokens, temperature, system_prompt):
        """Call the Groq API (OpenAI-compatible)."""
        import requests

        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._groq_key}",
            "Content-Type": "application/json",
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": self._groq_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_new_tokens,
            "response_format": {"type": "json_object"},
        }

        for attempt in range(5):
            resp = requests.post(url, json=body, headers=headers, timeout=60)
            if resp.status_code == 429:
                wait = 2 ** attempt * 3
                self.logger.warning("Rate limited (429), waiting %ds...", wait)
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                self.logger.error("Groq API error %d: %s", resp.status_code, resp.text[:300])
                raise RuntimeError(f"Groq API returned {resp.status_code}")
            break
        else:
            raise RuntimeError("Groq API rate limit exceeded after 5 retries")

        data = resp.json()
        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError):
            self.logger.error("Unexpected Groq response: %s", json.dumps(data)[:300])
            return ""

    def _generate_local(self, prompt, max_new_tokens, temperature, system_prompt):
        """Generate text using a locally loaded model."""
        import torch

        if self._has_chat_template:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            text = self.tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
        else:
            full = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
            inputs = self.tokenizer(full, return_tensors="pt").to(self.device)

        input_length = inputs["input_ids"].shape[1]
        gen_kwargs = dict(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=self.do_sample,
            temperature=temperature,
            top_p=self.top_p,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        if self.repetition_penalty and self.repetition_penalty != 1.0:
            gen_kwargs["repetition_penalty"] = self.repetition_penalty

        with torch.no_grad():
            outputs = self.model.generate(**gen_kwargs)

        new_tokens = outputs[0][input_length:]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True).strip()

    # ── JSON generation with retry ───────────────────────────────

    def generate_json(self, prompt, max_new_tokens=512, temperature=0.7,
                       system_prompt=None, schema_keys=None, max_retries=2):
        """Generate and parse JSON from the model output, with retry on failure."""
        raw = self.generate(prompt, max_new_tokens, temperature, system_prompt)
        result = self._parse_json(raw)

        attempt = 0
        while attempt < max_retries and (
            result is None
            or not isinstance(result, dict)
            or (schema_keys and not all(k in result for k in schema_keys))
        ):
            attempt += 1
            if result is None:
                reason = "invalid JSON"
            elif not isinstance(result, dict):
                reason = f"non-dict JSON ({type(result).__name__})"
            else:
                reason = "missing required keys"
            self.logger.warning("Retry %d/%d (%s), re-prompting...", attempt, max_retries, reason)
            retry_prompt = (
                "Your previous response was not valid JSON or was missing required fields. "
                "Please respond ONLY with a valid JSON object, no extra text before or after.\n\n"
                + prompt
            )
            raw = self.generate(retry_prompt, max_new_tokens, temperature, system_prompt)
            result = self._parse_json(raw)

        if isinstance(result, dict) and schema_keys:
            missing = [k for k in schema_keys if k not in result]
            if missing:
                self.logger.warning("JSON missing keys after retries: %s", missing)

        return result, raw

    @staticmethod
    def _parse_json(text):
        """Extract first JSON object or array from text, with auto-fix for common errors."""
        # Strip markdown code fences (```json ... ```)
        text = re.sub(r'```(?:json)?\s*', '', text)
        text = text.replace('```', '')
        for s, e in [("{", "}"), ("[", "]")]:
            start = text.find(s)
            if start == -1:
                continue
            depth = 0
            for i in range(start, len(text)):
                if text[i] == s:
                    depth += 1
                elif text[i] == e:
                    depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    try:
                        return json.loads(candidate)
                    except json.JSONDecodeError:
                        fixed = re.sub(r'"\s*\n\s*"', '",\n"', candidate)
                        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
                        try:
                            return json.loads(fixed)
                        except json.JSONDecodeError:
                            break
        return None
