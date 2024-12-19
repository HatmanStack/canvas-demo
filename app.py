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

def update_mask_editor(img):
    if img['background'] is None:
        return None
    return create_padded_image(img)

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
        ::-webkit-scrollbar {
            display: none; 
        }
        #component-0 {
            max-width: 800px;
            margin: 0 auto; 
        }
        .center-markdown {
            text-align: center !important;
            display: flex !important;
            justify-content: center !important;
            width: 100% !important;
        }
        
    </style>
    """)
    gr.Markdown("<h1>Amazon Nova Canvas Image Generation</h1>", elem_classes="center-markdown" )

    with gr.Tab("Text to Image"):
        with gr.Column():
            gr.Markdown("""
                Generate an image from a text prompt using the Amazon Nova Canvas model.
            """, elem_classes="center-markdown")
            prompt = gr.Textbox(label="Prompt", placeholder="Enter a text prompt (1-1024 characters)", max_lines=4)
            gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            error_box = gr.Markdown(visible=False, label="Error", elem_classes="center-markdown")
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            gr.Button("Generate").click(text_to_image, inputs=[prompt, negative_text, height, width, quality, cfg_scale, seed], outputs=[output, error_box])

    with gr.Tab("Inpainting"):
        with gr.Column():
            gr.Markdown("""
            
                Modify specific areas of your image using inpainting. Upload your base Image then choose one of two ways to specify the areas you want to edit: 
                You can use the in app editing tool to draw masks for areas to edit or use the Mask Prompt field to direct the model how to infer the mask.  <b>ONLY 
                ONE</b> of these methods can be used at a time.  Create an optional prompt to tell the model how to fill in the area you mask.
           
            """, elem_classes="center-markdown")
            mask_image = gr.ImageEditor(
                type="pil",
                height="100%",
                width="100%",
                crop_size="1:1",
                brush={"color": "#000000", "radius": 25},
                show_download_button=False,
                show_share_button=False,
                sources = ["upload"],
                transforms = None,
                layers = False,
                label="Draw mask (black areas will be edited)",
            )
            with gr.Accordion("Optional Mask Prompt", open=False):
                mask_prompt = gr.Textbox(label="Mask Prompt", placeholder="Describe regions to edit", max_lines=1)
            prompt = gr.Textbox(label="Optional Prompt", placeholder="Describe what to generate (1-1024 characters) in the masked area", max_lines=4)
            gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            error_box = gr.Markdown(visible=False, label="Error", elem_classes="center-markdown")
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            
            gr.Button("Generate").click(inpainting, inputs=[mask_image,mask_prompt, prompt, negative_text, height, width, quality, cfg_scale, seed], outputs=[output, error_box])

    with gr.Tab("Outpainting"):
        with gr.Column():
            gr.Markdown("""
                Modify areas outside of your image using outpainting. Give the image a transparent border by adding padding then draw
                a mask on the image or border where you would like the model to generate new content.  The other option is to allow the model to infer the mask from the Mask Prompt.  In options, you can choose to precisley follow the mask or transition smoothly 
                between the masked area and the non-masked area.  Create an optional prompt to tell the model how to fill in the area you mask.
            """, elem_classes="center-markdown")
            mask_image = gr.ImageEditor(
                type="pil",
                height="100%",
                width="100%",
                crop_size="1:1",
                brush=False,
                show_download_button=False,
                show_share_button=False,
                sources = ["upload"],
                layers = False,
                label="Crop the Image (transparent areas will be edited)"
            )
            gr.Button("Create Padding").click(fn=update_mask_editor, inputs=[mask_image], outputs=[mask_image])
            
            with gr.Accordion("Optional Mask Prompt", open=False):
                mask_prompt = gr.Textbox(label="Mask Prompt", placeholder="Describe regions to edit", max_lines=1)
            prompt = gr.Textbox(label="Prompt", placeholder="Describe what to generate (1-1024 characters)", max_lines=4)
            gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            error_box = gr.Markdown(visible=False, label="Error", elem_classes="center-markdown")
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                outpainting_mode = gr.Radio(choices=["DEFAULT", "PRECISE"], value="DEFAULT", label="Outpainting Mode")
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            
            gr.Button("Generate").click(outpainting, inputs=[mask_image, mask_prompt, prompt, negative_text, outpainting_mode, height, width, quality, cfg_scale, seed], outputs=[output, error_box])

    with gr.Tab("Image Variation"):
        with gr.Column():
            gr.Markdown("""
                Create a variation image based on up to 5 other images and a Similarity slider available in options.  You can add a prompt to direct the model (optional).  Images should be .png or .jpg.  
            """, elem_classes="center-markdown")
            images = gr.File(type='filepath', label="Input Images", file_count="multiple", file_types=["image"])
            with gr.Accordion("Optional Prompt", open=False):
                prompt = gr.Textbox(label="Prompt", placeholder="Enter a text prompt (1-1024 characters)", max_lines=4)
                gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            error_box = gr.Markdown(visible=False, label="Error", elem_classes="center-markdown")
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                similarity_strength = gr.Slider(minimum=0.2, maximum=1.0, step=0.1, value=0.7, label="Similarity Strength")
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            
            gr.Button("Generate").click(image_variation, inputs=[images, prompt, negative_text, similarity_strength, height, width, quality, cfg_scale, seed], outputs=[output, error_box])

    with gr.Tab("Image Conditioning"):
        with gr.Column():
            gr.Markdown("""
                Generate an image conditioned by an input image.  You need to add a text prompt to direct the model (required).
                You have two modes to control the conditioning,"CANNY" and "SEGMENTATION".  CANNY will follow the edges of the conditioning image closely.
                SEGMENTATION will follow the layout or shapes of the conditioning image. 
            """, elem_classes="center-markdown")
            condition_image = gr.Image(type='pil', label="Condition Image")
            prompt = gr.Textbox(label="Prompt", placeholder="Enter a text prompt (1-1024 characters)", max_lines=4)
            gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            error_box = gr.Markdown(visible=False, label="Error", elem_classes="center-markdown")
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                control_mode = gr.Radio(choices=["CANNY_EDGE", "SEGMENTATION"], value="CANNY_EDGE", label="Control Mode")
                control_strength = gr.Slider(minimum=0.0, maximum=1.0, step=0.1, value=0.7, label="Control Strength")
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            gr.Button("Generate").click(image_conditioning, inputs=[condition_image, prompt, negative_text, control_mode, control_strength, height, width, quality, cfg_scale, seed], outputs=[output, error_box])

    with gr.Tab("Color Guided"):
        with gr.Column():
            gr.Markdown("""
                Generate an image using a color palette.  This mode requires a text prompt and a color list.  If you choose to include an image, the subject and style will be used as a reference. 
                The colors of the image will also be incorporated, along with the colors from the colors list. A generic color list has been provided behind the scenes if one isn't added.
            """, elem_classes="center-markdown")
            with gr.Row():
                with gr.Column(scale=75): 
                    colors = gr.Textbox(label="Colors", placeholder="Enter up to 10 colors as hex values, e.g., #00FF00,#FCF2AB", max_lines=1)
                with gr.Column(scale=25):  
                    color_picker = gr.ColorPicker(label="Color Picker", show_label=False)
                    #add_color_button = gr.Button("Add Color")  Work out Color Picker Collapsing and Rerendering
                    #add_color_button.click(fn=add_color_to_list, inputs=[colors, color_picker], outputs=colors)
            prompt = gr.Textbox(label="Text", placeholder="Enter a text prompt (1-1024 characters)", max_lines=4)
            gr.Button("Generate Prompt").click(generate_nova_prompt, outputs=prompt)
            with gr.Accordion("Optional Reference Image", open=False):
                reference_image = gr.Image(type='pil', label="Reference Image")   
            error_box = gr.Markdown(visible=False, label="Error", elem_classes="center-markdown")
            output = gr.Image()
            with gr.Accordion("Advanced Options", open=False):
                negative_text, width, height, quality, cfg_scale, seed = create_advanced_options()
            gr.Button("Generate").click(color_guided_content, inputs=[prompt, reference_image, negative_text, colors, height, width, quality, cfg_scale, seed], outputs=[output, error_box])

    with gr.Tab("Background Removal"):
        with gr.Column():
            gr.Markdown("""
                Remove the background from an image.
            """, elem_classes="center-markdown")
            image = gr.Image(type='pil', label="Input Image")
            error_box = gr.Markdown(visible=False, label="Error", elem_classes="center-markdown")
            output = gr.Image()
            gr.Button("Generate").click(background_removal, inputs=image, outputs=[output, error_box])

    with gr.Accordion("Tips", open=False):
        gr.Markdown("On Inference Speed: Resolution (width/height), and quality all have an impact on Inference Speed.")
        gr.Markdown("On Negation: For example, consider the prompt \"a rainy city street at night with no people\". The model might interpret \"people\" as a directive of what to include instead of omit. To generate better results, you could use the prompt \"a rainy city street at night\" with a negative prompt \"people\".")
        gr.Markdown("On Prompt Length: When diffusion models were first introduced, they could process only 77 tokens. While new techniques have extended this limit, they remain bound by their training data. AWS Nova Canvas limits input by character length instead, ensuring no characters beyond the set limit are considered in the generated model.")

    gr.Markdown("""<h1>Sample Prompts and Results</h1>""", elem_classes="center-markdown")
    
    # Example 1
    with gr.Row():
        with gr.Column():
            gr.Image("examples/sample2.png", width=200, show_label=False, show_download_button=False, show_share_button=False, container=False)
        with gr.Column():
            gr.Markdown("""A whimsical outdoor scene where vibrant flowers and sprawling vines, crafted from an array of colorful fruit leathers and intricately designed candies, flutter with delicate, lifelike butterflies made from translucent, shimmering sweets. Each petal and leaf glistens with a soft, sugary sheen, casting playful reflections. The butterflies, with their candy wings adorned in fruity patterns, flit about, creating a magical, edible landscape that delights the senses.""")
    
    # Example 2
    with gr.Row():
        with gr.Column():
            gr.Image("examples/sample3.png", width=200, show_label=False, show_download_button=False, show_share_button=False, container=False)
        with gr.Column():
            gr.Markdown("""A Kansas Jayhawk with a basketball photorealistic""")

    # Example 3
    with gr.Row():
        with gr.Column():
            gr.Image("examples/sample4.png", width=200, show_label=False, show_download_button=False, show_share_button=False, container=False)
        with gr.Column():
            gr.Markdown("""A rugged adventurer's ensemble, crafted for the wild, featuring a khaki jacket adorned with numerous functional pockets, a sun-bleached pith hat with a wide brim, sturdy canvas trousers with reinforced knees, and a pair of weathered leather boots with high-traction soles. Accented with a brass compass pendant and a leather utility belt laden with small tools, the outfit is completed by a pair of aviator sunglasses and a weathered map tucked into a side pocket.""")



if __name__ == "__main__":
    demo.launch()



