"""Placeholder GUI application using Gradio (web-based).

Install with:  pip install gradio

Launch with:   python -m yt_lang_spreader.gui.app

This is a scaffold — fill in the callbacks to connect to the pipeline.
"""

from __future__ import annotations


def launch_gui() -> None:
    """Launch the Gradio web UI."""
    try:
        import gradio as gr
    except ImportError:
        print(
            "Gradio is not installed. Install it with:\n"
            "  pip install gradio\n"
            "Then re-run this command."
        )
        return

    from ..core.config import PipelineConfig
    from ..core.pipeline import run_pipeline

    def process_video(
        url: str,
        target_lang: str,
        compression: int,
        tts_backend: str,
        elevenlabs_voice_id: str,
        enable_stock_charts: bool,
    ) -> str:
        config = PipelineConfig(
            url=url,
            target_lang=target_lang,
            compression_level=int(compression),
            tts_backend=tts_backend,
            elevenlabs_voice_id=elevenlabs_voice_id,
            enable_stock_charts=enable_stock_charts,
        )
        try:
            output_path = run_pipeline(config)
            return f"Video created: {output_path}"
        except Exception as e:
            return f"Error: {e}"

    with gr.Blocks(title="YouTube Language Spreader") as app:
        gr.Markdown("# YouTube Language Spreader")
        gr.Markdown(
            "Summarize, translate, and narrate YouTube videos in any language."
        )

        with gr.Row():
            url_input = gr.Textbox(
                label="YouTube URL", placeholder="https://youtu.be/..."
            )
            lang_input = gr.Dropdown(
                label="Target Language",
                choices=["zh", "es", "fr", "de", "ja", "ko", "pt", "ru"],
                value="zh",
            )

        with gr.Row():
            compression_input = gr.Slider(
                label="Compression Level", minimum=1, maximum=5, step=1, value=3
            )
            tts_input = gr.Dropdown(
                label="TTS Backend",
                choices=["gtts", "elevenlabs", "openai_tts", "local"],
                value="gtts",
            )

        with gr.Row():
            voice_id_input = gr.Textbox(
                label="ElevenLabs Voice ID (optional)",
                placeholder="Leave blank for default",
            )
            stock_charts_input = gr.Checkbox(
                label="Enable Stock Charts", value=False
            )

        run_btn = gr.Button("Process Video", variant="primary")
        output_text = gr.Textbox(label="Result", interactive=False)

        run_btn.click(
            fn=process_video,
            inputs=[
                url_input,
                lang_input,
                compression_input,
                tts_input,
                voice_id_input,
                stock_charts_input,
            ],
            outputs=output_text,
        )

    app.launch()


if __name__ == "__main__":
    launch_gui()
