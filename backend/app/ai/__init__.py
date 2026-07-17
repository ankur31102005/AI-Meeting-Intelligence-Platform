"""AI subsystem: audio processing, transcription, (later) diarization,
intelligence, embeddings. Every heavy dependency is imported lazily inside
the concrete provider so the API process boots without the ML stack."""
