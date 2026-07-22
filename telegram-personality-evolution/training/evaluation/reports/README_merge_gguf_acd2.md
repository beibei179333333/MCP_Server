# 合并 + GGUF 量化

## 前置

1. Stage3 训完：`output/qwen_full_stage3` 含 `adapter_config.json`
2. 合并依赖：`pip install transformers peft accelerate torch safetensors`
3. GGUF 依赖：clone [llama.cpp](https://github.com/ggerganov/llama.cpp)，编译 `llama-quantize`，并：
   ```bash
   export LLAMA_CPP_DIR=/path/to/llama.cpp
   ```

## 命令

```bash
# 合并 LoRA
python merge_lora.py --base Qwen/Qwen3-27B --lora output/qwen_full_stage3 --output qwen_beibei_final

# 量化成 GGUF（便于本地部署）
python convert_to_gguf.py qwen_beibei_final --outtype q4_k_m
```

## 产物

| 路径 | 说明 |
|------|------|
| `qwen_beibei_final/` | 合并后的完整 HF 模型 |
| `qwen_beibei_final/qwen_beibei_final-q4_k_m.gguf` | Q4_K_M 量化包 |

可用 Ollama / llama.cpp / LM Studio 加载 GGUF。
