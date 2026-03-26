from pathlib import Path

import gradio as gr

from src.handlers.canvas_handlers import canvas_handlers
from src.handlers.health import health_checker
from src.models.config import get_config
from src.utils.lambda_helpers import lambda_image_handler
from src.utils.logger import app_logger

app_logger.info("Starting Canvas Demo application")

def append_color(current_colors: str, new_color: str) -> str:
    """Append a color picker selection to the colors textbox."""
    if not current_colors or not current_colors.strip():
        return new_color
    return f"{current_colors},{new_color}"


def create_advanced_options():
    """Create reusable advanced options components"""
    app_logger.debug("Creating advanced options UI components")

    negative_text = gr.Textbox(
        label="Negative Prompt",
        placeholder="Describe what not to include (1-1024 characters)",
        max_lines=1
    )
    width = gr.Slider(
        minimum=get_config().min_image_size,
        maximum=get_config().max_image_size,
        step=get_config().step_size,
        value=get_config().default_size,
        label="Width"
    )
    height = gr.Slider(
        minimum=get_config().min_image_size,
        maximum=get_config().max_image_size,
        step=get_config().step_size,
        value=get_config().default_size,
        label="Height"
    )
    quality = gr.Radio(
        choices=["standard", "premium"],
        value="standard",
        label="Quality"
    )
    cfg_scale = gr.Slider(
        minimum=1.0,
        maximum=20.0,
        step=0.1,
        value=get_config().default_cfg_scale,
        label="CFG Scale"
    )
    seed = gr.Slider(
        minimum=1,
        maximum=2000,
        step=1,
        value=get_config().default_seed,
        label="Seed"
    )

    return negative_text, width, height, quality, cfg_scale, seed

# Gradio Interface with optimized structure
app_logger.info("Setting up Gradio interface")

_static = Path(__file__).parent / "static"
_error_js = (_static / "error_interceptor.js").read_text()
_app_css = (_static / "app.css").read_text()

error_interceptor_script = f"<script>{_error_js}</script>"

with gr.Blocks(title="AWS Nova Canvas", head=error_interceptor_script, css=_app_css) as demo:

    gr.Markdown("""
        <h1>AWS Nova Canvas Image Generation</h1>
        <p>High-performance image generation</p>
    """, elem_classes="center-markdown")

    # Text to Image Tab
    with gr.Tab("Text to Image"):
        with gr.Column():
            gr.Markdown("""
                Generate an image from a text prompt using the AWS Nova Canvas model.
            """, elem_classes="center-markdown")

            output = gr.Image(label="Generated Image")

            with gr.Accordion("Advanced Options", open=False):
                txt2img_negative_text, txt2img_width, txt2img_height, txt2img_quality, txt2img_cfg_scale, txt2img_seed = create_advanced_options()

            txt2img_prompt = gr.Textbox(
                label="Prompt",
                placeholder="Enter a text prompt (1-1024 characters)",
                max_lines=4
            )
            txt2img_error_box = gr.Markdown(visible=False, elem_classes="error-message")

            with gr.Row():
                gr.Button("Generate Prompt").click(
                    canvas_handlers.generate_nova_prompt,
                    outputs=txt2img_prompt
                )
                gr.Button("Generate Image", elem_id="text_to_image_generate_button").click(
                    canvas_handlers.text_to_image,
                    inputs=[txt2img_prompt, txt2img_negative_text, txt2img_height, txt2img_width, txt2img_quality, txt2img_cfg_scale, txt2img_seed],
                    outputs=[output, txt2img_error_box]
                )

    # Inpainting Tab
    with gr.Tab("Inpainting"):
        with gr.Column():
            gr.Markdown("""
            Modify specific areas of your image using inpainting. Upload your base image, then specify areas to edit.
            """, elem_classes="center-markdown")

            mask_image = gr.ImageMask(type="pil", label="Draw mask (black areas will be edited)")

            with gr.Accordion("Optional Mask Prompt", open=False):
                mask_prompt = gr.Textbox(
                    label="Mask Prompt",
                    placeholder="Describe regions to edit",
                    max_lines=1
                )

            with gr.Accordion("Advanced Options", open=False):
                inpaint_negative_text, inpaint_width, inpaint_height, inpaint_quality, inpaint_cfg_scale, inpaint_seed = create_advanced_options()

            inpaint_error_box = gr.Markdown(visible=False, elem_classes="error-message")
            inpaint_prompt = gr.Textbox(
                label="Prompt",
                placeholder="Describe what to generate in the masked area",
                max_lines=4
            )
            inpaint_output = gr.Image(label="Generated Image")

            with gr.Row():
                gr.Button("Generate Prompt").click(
                    canvas_handlers.generate_nova_prompt,
                    outputs=inpaint_prompt
                )
                gr.Button("Generate Image").click(
                    canvas_handlers.inpainting,
                    inputs=[mask_image, mask_prompt, inpaint_prompt, inpaint_negative_text, inpaint_height, inpaint_width, inpaint_quality, inpaint_cfg_scale, inpaint_seed],
                    outputs=[inpaint_output, inpaint_error_box]
                )

    # Outpainting Tab
    with gr.Tab("Outpainting"):
        with gr.Column():
            gr.Markdown("""
                Extend your image boundaries using outpainting. Add transparent padding and position your base image.
            """, elem_classes="center-markdown")

            outpaint_mask_image = gr.ImageMask(type="pil", label="Draw mask (white areas will be edited)")

            gr.Button("Create Padding").click(
                fn=canvas_handlers.update_mask_editor,
                inputs=[outpaint_mask_image],
                outputs=[outpaint_mask_image]
            )

            with gr.Accordion("Optional Mask Prompt", open=False):
                outpaint_mask_prompt = gr.Textbox(
                    label="Mask Prompt",
                    placeholder="Describe regions to edit",
                    max_lines=1
                )

            with gr.Accordion("Advanced Options", open=False):
                outpainting_mode = gr.Radio(
                    choices=["DEFAULT", "PRECISE"],
                    value="DEFAULT",
                    label="Outpainting Mode"
                )
                outpaint_negative_text, outpaint_width, outpaint_height, outpaint_quality, outpaint_cfg_scale, outpaint_seed = create_advanced_options()

            outpaint_error_box = gr.Markdown(visible=False, elem_classes="error-message")
            outpaint_prompt = gr.Textbox(
                label="Prompt",
                placeholder="Describe what to generate",
                max_lines=4
            )
            outpaint_output = gr.Image(label="Generated Image")

            with gr.Row():
                gr.Button("Generate Prompt").click(
                    canvas_handlers.generate_nova_prompt,
                    outputs=outpaint_prompt
                )
                gr.Button("Generate Image").click(
                    canvas_handlers.outpainting,
                    inputs=[outpaint_mask_image, outpaint_mask_prompt, outpaint_prompt, outpaint_negative_text, outpainting_mode, outpaint_height, outpaint_width, outpaint_quality, outpaint_cfg_scale, outpaint_seed],
                    outputs=[outpaint_output, outpaint_error_box]
                )

    # Image Variation Tab
    with gr.Tab("Image Variation"):
        with gr.Column():
            gr.Markdown("""
                Create variations based on up to 5 input images with adjustable similarity.
            """, elem_classes="center-markdown")

            images = gr.File(
                type='filepath',
                label="Input Images",
                file_count="multiple",
                file_types=["image"]
            )

            with gr.Accordion("Optional Prompt", open=False):
                prompt = gr.Textbox(
                    label="Prompt",
                    placeholder="Enter a text prompt",
                    max_lines=4
                )
                gr.Button("Generate Prompt").click(
                    canvas_handlers.generate_nova_prompt,
                    outputs=prompt
                )

            with gr.Accordion("Advanced Options", open=False):
                similarity_strength = gr.Slider(
                    minimum=0.2,
                    maximum=1.0,
                    step=0.1,
                    value=0.7,
                    label="Similarity Strength"
                )
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()

            error_box = gr.Markdown(visible=False, elem_classes="error-message")
            output = gr.Image(label="Generated Image")

            gr.Button("Generate Image").click(
                canvas_handlers.image_variation,
                inputs=[images, prompt, negative_text, similarity_strength, height, width, quality, cfg_scale, seed],
                outputs=[output, error_box]
            )

    # Image Conditioning Tab
    with gr.Tab("Image Conditioning"):
        with gr.Column():
            gr.Markdown("""
                Generate images conditioned by an input image with CANNY or SEGMENTATION modes.
            """, elem_classes="center-markdown")

            condition_image = gr.Image(type='pil', label="Condition Image")

            with gr.Accordion("Advanced Options", open=False):
                control_mode = gr.Radio(
                    choices=["CANNY_EDGE", "SEGMENTATION"],
                    value="CANNY_EDGE",
                    label="Control Mode"
                )
                control_strength = gr.Slider(
                    minimum=0.0,
                    maximum=1.0,
                    step=0.1,
                    value=0.7,
                    label="Control Strength"
                )
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()

            error_box = gr.Markdown(visible=False, elem_classes="error-message")
            prompt = gr.Textbox(
                label="Prompt",
                placeholder="Enter a text prompt (required)",
                max_lines=4
            )
            output = gr.Image(label="Generated Image")

            with gr.Row():
                gr.Button("Generate Prompt").click(
                    canvas_handlers.generate_nova_prompt,
                    outputs=prompt
                )
                gr.Button("Generate Image").click(
                    canvas_handlers.image_conditioning,
                    inputs=[condition_image, prompt, negative_text, control_mode, control_strength, height, width, quality, cfg_scale, seed],
                    outputs=[output, error_box]
                )

    # Color Guided Tab
    with gr.Tab("Color Guided"):
        with gr.Column():
            gr.Markdown("""
                Generate images using a color palette with optional reference image.
            """, elem_classes="center-markdown")

            with gr.Row():
                with gr.Column(scale=70):
                    colors = gr.Textbox(
                        label="Colors",
                        placeholder="Enter up to 10 colors as hex values, e.g., #00FF00,#FCF2AB",
                        max_lines=1
                    )
                with gr.Column(scale=30):
                    color_picker = gr.ColorPicker(
                        label="Color Picker",
                        show_label=False,
                        value='#473c80',
                        interactive=True
                    )

            color_picker.change(append_color, inputs=[colors, color_picker], outputs=colors)

            with gr.Accordion("Advanced Options", open=False):
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()

            with gr.Accordion("Optional Reference Image", open=False):
                reference_image = gr.Image(type='pil', label="Reference Image")

            error_box = gr.Markdown(visible=False, elem_classes="error-message")
            prompt = gr.Textbox(
                label="Prompt",
                placeholder="Enter a text prompt (required)",
                max_lines=4
            )
            output = gr.Image(label="Generated Image")

            with gr.Row():
                gr.Button("Generate Prompt").click(
                    canvas_handlers.generate_nova_prompt,
                    outputs=prompt
                )
                gr.Button("Generate Image").click(
                    canvas_handlers.color_guided_content,
                    inputs=[prompt, reference_image, negative_text, colors, height, width, quality, cfg_scale, seed],
                    outputs=[output, error_box]
                )

    # Background Removal Tab
    with gr.Tab("Background Removal"), gr.Column():
        gr.Markdown("""
                Remove the background from an image.
            """, elem_classes="center-markdown")

        image = gr.Image(type='pil', label="Input Image")
        error_box = gr.Markdown(visible=False, elem_classes="error-message")
        output = gr.Image(label="Processed Image")

        gr.Button("Remove Background").click(
            canvas_handlers.background_removal,
            inputs=image,
            outputs=[output, error_box]
        )

    # Tips and Health Status
    with gr.Tab("System Info"), gr.Column():
        gr.Markdown("## Performance Tips", elem_classes="center-markdown")
        gr.Markdown("""
            - **Resolution & Quality**: Higher settings increase processing time
            - **Negative Prompts**: Use specific terms in negative prompts for better results
            - **Prompt Length**: Keep prompts under 1000 characters for optimal performance
            """)

        gr.Markdown("## System Health", elem_classes="center-markdown")
        health_display = gr.JSON(label="Health Status")
        gr.Button("Refresh Health Status").click(
            health_checker.get_health_status,
            outputs=health_display
        )

app_logger.info("Gradio interface setup completed")

# Application launch logic
if __name__ == "__main__":
    app_logger.info("Starting application launch sequence")

    # Clean up any old temporary files in Lambda environment
    if get_config().is_lambda:
        lambda_image_handler.cleanup_temp_files(max_age_seconds=1800)  # 30 minutes

        app_logger.info(f"Launching for Lambda on port {get_config().lambda_port}")
        demo.launch(
            server_name="0.0.0.0",
            server_port=get_config().lambda_port,
            show_error=True
        )

    else:
        app_logger.info("Launching for local development")
        demo.launch(
            debug=True,
            show_error=True
        )
