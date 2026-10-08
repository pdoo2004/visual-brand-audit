# Development model for tone scoring

Sprint 1, backlog 4.1. The locked rubric sends only **B1, Tone and approachability**, to the vision-language model. The placeholder target tone is “approachable, competent.” Exposure, contrast, color palette, framing, and sharpness stay with the computer-vision analyzer.

The design document names Gemma 4 31B for the dedicated GPU host and a smaller Gemma 4 model for development. This note is the laptop comparison that picked the development model.

## Sample set

The same three public photographs and the same B1 prompt were used for every model that could load. Sources and licenses are in `samples/manifest.json`. These files are the benchmark set. They are not a fine-tuning set.

| File | Scene | Why it is in the set |
|---|---|---|
| `samples/01-coffee-shop.jpg` | Hands, a cup, latte art, warm light | Should fit the target tone |
| `samples/02-glass-office.jpg` | Bright office, one person, desks, monitors, plants | Should fit a competent workplace tone |
| `samples/03-neon-city.jpg` | Night city behind a blue neon mesh, no people | A sharp technical photo that should score low on approachability |

## Result

**Development model: `gemma4:e4b`.**

| Model | Role in this project | Ran on the dev laptop | What it did on B1 |
|---|---|---|---|
| `gemma4:e4b` | Development model | Yes. About 5.7 GB of a 6 GB GPU. About 2 seconds per photo after load. | JSON for B1 only. Coffee and office scored 4. Neon city scored 2. |
| `gemma4:e2b` | Smaller Gemma 4 candidate | Yes. About 4.3 GB. About 1 second per photo after load. | JSON for B1 only, but the neon city scored 4, and the criterion name was copied wrong. |
| `gemma4:26b` | Larger Gemma 4 candidate | No. Weights are 18 GB. | Left for the GPU host. |
| `gemma4:31b` | Design-doc server model | Not pulled. Weights are about 20 GB at 4-bit and about 70 GB at 16-bit. | Still the candidate for vLLM on the cloud GPU (backlog 4.4 and 7.10). |
| `qwen2.5:7b` | Already installed locally | No | Text only. It cannot judge a photograph. |

Raw runs: `results/gemma4_e4b.json` and `results/gemma4_e2b.json`.

E4B is the development model because it changed the score when the photograph changed, and it fits the machines we use day to day. A warm reply is about 2 seconds. Keep the context at 2048 tokens on a 6 GB GPU.

31B is not rejected. It needs the separate GPU host. The backend should keep calling an HTTP endpoint so the development model and the server model can be swapped without changing the scorer.
