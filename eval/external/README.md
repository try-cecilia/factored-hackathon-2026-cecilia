# External data: MInDS-14 (es-ES, pt-PT)

`minds14-es-pt.tsv` holds the transcriptions of **MInDS-14** for the Spanish (Spain) and Portuguese (Portugal) configurations:
1,090 calls to an e-banking line, transcribed by ASR, each with the dataset's own intent label.

- **Source:** PolyAI, `PolyAI/minds14` on Hugging Face (https://huggingface.co/datasets/PolyAI/minds14), `train` split of the `es-ES` and `pt-PT` configurations, read through the Hugging Face datasets server on 2026-10-01. Audio is not included.
- **License:** CC BY 4.0. Attribution: Gerz et al., "Multilingual and Cross-Lingual Intent Detection from Spoken Data" (PolyAI, 2021).
- **Columns:** `lang` (`es-ES`, `pt-PT`), `intent` (the dataset's, one of 14), `transcription` (tabs and line breaks replaced by spaces, nothing else changed), `clip` (the audio file's name).
- **What it is used for:** one zero-shot test of the intent classifier, `python -m eval.real_speech`. **It is never used for training, selection or tuning**, and a test (`tests/test_real_speech.py`) fails if any training or selection code names it.
- **Integrity:** the file's SHA-256 (with LF line endings) is fixed in `eval/real_speech.py`, so the protocol cannot silently run on a different file.
