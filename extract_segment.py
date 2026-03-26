#pip install "segment-geospatial[samgeo3]"
from huggingface_hub import login
import os
TOKEN=os.getenv("HF_TOKEN")
login(token=TOKEN)

# Initialize SAM3
from samgeo import SamGeo3
sam3 = SamGeo3(backend="meta", device=None, checkpoint_path=None, load_from_HF=True, confidence_threshold=0.4)

import os

def batch_segment_lakes(input_folder, output_folder, prompt="Water"):
    """
    Segments multiple TIFF images in a folder using SamGeo3 and saves the results in another folder.

    Parameters:
    - input_folder: str, path to folder containing input TIFF images
    - output_folder: str, path to folder where segmented TIFFs will be saved
    - prompt: str, prompt for SamGeo3 segmentation (default: "Water")
    """
    # Ensure output folder exists
    os.makedirs(output_folder, exist_ok=True)

    # Loop over all TIFF files in input folder
    for filename in os.listdir(input_folder):
        if filename.lower().endswith(".tif") or filename.lower().endswith(".tiff"):
            input_path = os.path.join(input_folder, filename)
            output_path = os.path.join(output_folder, filename.replace(".tiff", ".tif"))  # normalize extension

            print(f"Processing {filename}...")
            sam3.set_image(input_path)
            sam3.generate_masks(prompt=prompt)
            if sam3.masks is not None and len(sam3.masks) > 0:
                sam3.save_masks(output=output_path, unique=False)
                print(f"Saved segmented mask to {output_path}")
            else:
                print(f"No objects found in {filename}, skipping save.")
            print(f"Saved segmented mask to {output_path}")

    print("All images processed!")

# Usage example
for folder in os.listdir("lakes"):
    input_folder = f"lakes/{folder}"
    output_folder = f"/content/drive/MyDrive/lakes-segmented/{folder}"
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    batch_segment_lakes(input_folder, output_folder)