import gradio as gr
from functions import *
from dataclasses import dataclass

@dataclass
class Config:
    min_size: int = 256
    max_size: int = 2048
    step_size: int = 64
    default_size: int = 1024
    default_cfg_scale: float = 8.0
    default_seed: int = 8

config = Config()

def create_advanced_options():
    
    negative_text = gr.Textbox(label="Negative Prompt", placeholder="Describe what not to include (1-1024 characters)", max_lines=1)
    width = gr.Slider(minimum=config.min_size, maximum=config.max_size, step=config.step_size, value=config.default_size, label="Width")
    height = gr.Slider(minimum=config.min_size, maximum=config.max_size, step=config.step_size, value=config.default_size, label="Height")
    quality = gr.Radio(choices=["standard", "premium"], value="standard", label="Quality")
    cfg_scale = gr.Slider(minimum=1.0, maximum=20.0, step=0.1, value=config.default_cfg_scale, label="CFG Scale")
    seed = gr.Slider(minimum=1, maximum=2000, step=1, value=config.default_seed, label="Seed")
    return negative_text, width, height, quality, cfg_scale, seed

# Gradio Interface
with gr.Blocks() as demo:
    gr.HTML("""
    <style>
        #component-0 {
            max-width: 800px;
            margin: 0 auto; 
        }
    </style>
    """)
    gr.Markdown("# Amazon Nova Canvas Image Generation")

    with gr.Tab("Text to Image"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                        Generate an image from a text prompt using the Amazon Nova Canvas model.
             </div>
            """)
            prompt = gr.Textbox(label="Prompt", placeholder="Enter a text prompt (1-1024 characters)", max_lines=4)
            gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            gr.Button("Generate").click(text_to_image, inputs=[prompt, negative_text, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Inpainting"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Modify specific areas of your image using inpainting. Upload your image and choose one of two ways to specify the areas you want to edit: 
                You can use a photo editing tool to draw masks (using pure black for areas to edit and pure white for areas to preserve) or 
                use the Mask Prompt field to direct the model in how to infer the mask.  Create an optional prompt to tell the model how to fill in the area you mask.
            </div>
            """)
            image = gr.Image(type='pil', label="Input Image")
            with gr.Accordion("Optional Prompt", open=False):
                prompt = gr.Textbox(label="Prompt", placeholder="Describe what to generate (1-1024 characters)", max_lines=4)
                gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            mask_prompt = gr.Textbox(label="Mask Prompt", placeholder="Describe regions to edit", max_lines=1)
            with gr.Accordion("Mask Image", open=False):
                mask_image = gr.Image(type='pil', label="Mask Image")
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            
            gr.Button("Generate").click(inpainting, inputs=[image, mask_prompt, mask_image, prompt, negative_text, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Outpainting"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Modify areas outside of your image using outpainting. The image you upload should have some transparency around the edges that you'd like to outpaint
                into.  In options, you can choose to precisley follow the mask or transition smoothly between the masked area and the non-masked area. Choose one of two ways to specify the areas you want to edit: 
                You can use a photo editing tool to draw masks extended outside of an images original borders (using pure black for areas to edit and pure 
                white for areas to preserve) or use the Mask Prompt field to direct the model in how to infer the mask. Create an optional prompt to tell the model how to fill in the area you mask.
            </div>
            """)
            image = gr.Image(type='pil', label="Input Image")
            with gr.Accordion("Optional Prompt", open=False):
                prompt = gr.Textbox(label="Prompt", placeholder="Describe what to generate (1-1024 characters)", max_lines=4)
                gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            mask_prompt = gr.Textbox(label="Mask Prompt", placeholder="Describe regions to edit", max_lines=1)
            with gr.Accordion("Mask Image", open=False):
                mask_image = gr.Image(type='pil', label="Mask Image")
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                outpainting_mode = gr.Radio(choices=["DEFAULT", "PRECISE"], value="DEFAULT", label="Outpainting Mode")
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            
            gr.Button("Generate").click(outpainting, inputs=[image, mask_prompt, mask_image, prompt, negative_text, outpainting_mode, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Image Variation"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Create a variation image based on up to 5 other images and a Similarity slider available in options.  You can add a prompt to direct the model (optional).  Images should be .png or .jpg.
                </div>
            """)
            images = gr.File(type='filepath', label="Input Images", file_count="multiple", file_types=["image"])
            with gr.Accordion("Optional Prompt", open=False):
                prompt = gr.Textbox(label="Prompt", placeholder="Enter a text prompt (1-1024 characters)", max_lines=4)
                gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                similarity_strength = gr.Slider(minimum=0.2, maximum=1.0, step=0.1, value=0.7, label="Similarity Strength")
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            
            gr.Button("Generate").click(image_variation, inputs=[images, prompt, negative_text, similarity_strength, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Image Conditioning"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Generate an image conditioned by an input image.  You need to add a text prompt to direct the model (required).
                You have two modes to control the conditioning,"CANNY" and "SEGMENTATION".  CANNY will follow the edges of the conditioning image closely.
                SEGMENTATION will follow the layout or shapes of the conditioning image. 
                </div>
            """)
            condition_image = gr.Image(type='pil', label="Condition Image")
            prompt = gr.Textbox(label="Prompt", placeholder="Enter a text prompt (1-1024 characters)", max_lines=4)
            gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                control_mode = gr.Radio(choices=["CANNY_EDGE", "SEGMENTATION"], value="CANNY_EDGE", label="Control Mode")
                control_strength = gr.Slider(minimum=0.0, maximum=1.0, step=0.1, value=0.7, label="Control Strength")
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            gr.Button("Generate").click(image_conditioning, inputs=[condition_image, prompt, negative_text, control_mode, control_strength, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Color Guided Content"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Generate an image using a color palette.  If you choose to include an image (optional) the subject and style will be used as a reference. 
                The colors of the image will also be incorporated, along with the colors from the colors list. A color list is always required but one has been provided.
                </div>
            """)
            reference_image = gr.Image(type='pil', label="Reference Image")     
            colors = gr.Textbox(label="Colors", placeholder="Enter up to 10 colors as hex values, e.g., #00FF00,#FCF2AB", max_lines=1)
            with gr.Accordion("Optional Prompt", open=False):
                prompt = gr.Textbox(label="Text", placeholder="Enter a text prompt (1-1024 characters)", max_lines=4)
                gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            gr.Button("Generate").click(color_guided_content, inputs=[prompt, reference_image, negative_text, colors, height, width, quality, cfg_scale, seed], outputs=output)

    with gr.Tab("Background Removal"):
        with gr.Column():
            gr.Markdown("""
            <div style="text-align: center;">
                Remove the background from an image.
                </div>
            """)
            image = gr.Image(type='pil', label="Input Image")
            output = gr.Image()
            gr.Button("Generate").click(background_removal, inputs=image, outputs=output)

    with gr.Accordion("Tips", open=False):
        gr.Markdown("On Inference Speed: Resolution (width/height), and quality all have an impact on Inference Speed.")
        gr.Markdown("On Negation: For example, consider the prompt \"a rainy city street at night with no people\". The model might interpret \"people\" as a directive of what to include instead of omit. To generate better results, you could use the prompt \"a rainy city street at night\" with a negative prompt \"people\".")
        gr.Markdown("On Prompt Length: When diffusion models were first introduced, they could process only 77 tokens. While new techniques have extended this limit, they remain bound by their training data. AWS Nova Canvas limits input by character length instead, ensuring no characters beyond the set limit are considered in the generated model.")
if __name__ == "__main__":
    demo.launch()



