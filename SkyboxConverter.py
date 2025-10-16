# The core conversion logic remains the same. The VMAT generation and configuration are updated.

from PIL import Image
import os
import sys
import glob
import time 
import textwrap

# --- VTR to Image Conversion Library ---
try:
    from vtf2img import Parser
except ImportError:
    print("Error: The 'vtf2img' library is required for VTF conversion.")
    print("Please install it using: pip install vtf2img")
    sys.exit(1) # Exit immediately if vtf2img is missing as it's a primary function

# --- Image Stitching Library ---
try:
    # Check if Pillow is imported correctly
    Image.new
except NameError:
    print("Error: The 'Pillow' library is required for image stitching.")
    print("Please install it using: pip install Pillow")
    sys.exit(1)

# --- EXR Support Library (Using openexr-numpy) ---
EXR_SUPPORT_ENABLED = False
try:
    import numpy as np
    from openexr_numpy import imread
    EXR_SUPPORT_ENABLED = True
    print("EXR Support: openexr-numpy is installed and ready for .exr files.")
except ImportError:
    print("Warning: The 'openexr-numpy' or 'numpy' library is not installed. .exr file support is unavailable.")

# --- CONFIGURATION ---
OUTPUT_DIR = "skybox" 
FINAL_OUTPUT_FILENAME = "skybox_jimi.png"
FINAL_SKYBOX_VMAT_FILENAME = "skybox_jimi.vmat" # Standard Skybox VMAT
FINAL_MOONDOME_VMAT_FILENAME = "moondome_jimi.vmat" # Moondome VMAT
INPUT_DIRECTORY = "." 
# Path for SkyTexture inside the VMAT (must use engine paths)
SKYTEXTURE_PATH = f"materials/{OUTPUT_DIR}/{FINAL_OUTPUT_FILENAME}"
# --- END CONFIGURATION ---

FINAL_OUTPUT_PATH = os.path.join(OUTPUT_DIR, FINAL_OUTPUT_FILENAME)
FINAL_SKYBOX_VMAT_PATH = os.path.join(OUTPUT_DIR, FINAL_SKYBOX_VMAT_FILENAME)
FINAL_MOONDOME_VMAT_PATH = os.path.join(OUTPUT_DIR, FINAL_MOONDOME_VMAT_FILENAME)


# --- VMAT TEMPLATE (LDR Only) ---
LDR_VMAT_CONTENT = f"""// THIS FILE IS AUTO-GENERATED (STANDARD SKYBOX)

Layer0
{{
	shader "sky.vfx"

	//---- Format ----
	F_TEXTURE_FORMAT2 1 // Dxt1 (LDR)

	//---- Texture ----
	g_flBrightnessExposureBias "0.000"
	g_flRenderOnlyExposureBias "0.000"
	SkyTexture "{SKYTEXTURE_PATH}"


	VariableState
	{{
		"Texture"
		{{
		}}
	}}
}}"""
# --------------------

# --- MOONDOME VMAT TEMPLATE (NEW) ---
MOONDOME_VMAT_CONTENT = f"""// THIS FILE IS AUTO-GENERATED (MOONDOME)

Layer0
{{
	shader "csgo_moondome.vfx"

	//---- Color ----
	g_flTexCoordRotation "0.000"
	g_nScaleTexCoordUByModelScaleAxis "0" // None
	g_nScaleTexCoordVByModelScaleAxis "0" // None
	g_vColorTint "[1.000000 1.000000 1.000000 0.000000]"
	g_vTexCoordCenter "[0.500 0.500]"
	g_vTexCoordOffset "[0.000 0.000]"
	g_vTexCoordScale "[1.000 1.000]"
	g_vTexCoordScrollSpeed "[0.000 0.000]"
	TextureColor "[1.000000 1.000000 1.000000 0.000000]"

	//---- CubeParallax ----
	g_flCubeParallax "0.000"

	//---- Fog ----
	g_bFogEnabled "1"

	//---- Texture ----
	TextureCubeMap "{SKYTEXTURE_PATH}"

	//---- Texture Address Mode ----
	g_nTextureAddressModeU "0" // Wrap
	g_nTextureAddressModeV "0" // Wrap


	VariableState
	{{
		"Color"
		{{
		}}
		"CubeParallax"
		{{
		}}
		"Fog"
		{{
		}}
		"Texture"
		{{
		}}
		"Texture Address Mode"
		{{
		}}
	}}
}}"""
# --------------------

def convert_exr_to_png(input_file, output_file):
    """
    Converts a single EXR file to a temporary LDR PNG file using openexr-numpy and PIL.
    """
    try:
        # Read the EXR file using openexr-numpy
        image_float = imread(input_file)

        # Handle channels (convert to RGBA)
        if image_float.shape[2] == 4:
            pass # Already RGBA
        elif image_float.shape[2] == 3:
            # Add an alpha channel of 1s if only RGB is present
            alpha = np.ones((image_float.shape[0], image_float.shape[1], 1), dtype=image_float.dtype)
            image_float = np.concatenate((image_float, alpha), axis=2)
        else:
            raise ValueError(f"EXR file has unexpected channel count: {image_float.shape[2]}")


        # Perform simple tone-mapping/normalization for LDR PNG (0-255).
        # We use a simple clip/scale for LDR conversion.
        clipped_image = np.clip(image_float, 0.0, 1.0) # Clips to 0-1 range

        # Convert to 8-bit unsigned integer (0-255)
        image_8bit = (clipped_image * 255).astype(np.uint8)

        # Use Pillow to save the 8-bit NumPy array as a PNG
        pil_image = Image.fromarray(image_8bit, 'RGBA') # Specify RGBA mode
        pil_image.save(output_file, format='PNG')
        
        return True
    
    except Exception as e:
        print(f"Error processing {input_file}: {e}")
        return False


def find_cubemap_files(directory="."):
    """
    Scans the specified directory for files matching the cubemap face keywords.
    Prints the names of any missing required face images.
    """
    FACE_KEYWORDS = {
        'back': ['back', 'bk'],
        'up':   ['up', 'top'],      
        'front':['front', 'ft'],
        'right':['right', 'rt'],
        'left': ['left', 'lf'],
        'down': ['down', 'dn'],     
    }
    REQUIRED_FACES = set(FACE_KEYWORDS.keys())
    # UPDATED: Added '.exr' back
    IMAGE_EXTENSIONS = ('.vtf', '.png', '.jpg', '.jpeg', '.tga', '.hdr', '.exr') 
    VMT_EXTENSION = ('.vmt',)
    ALL_EXTENSIONS = IMAGE_EXTENSIONS + VMT_EXTENSION

    found_files = {}
    
    all_files = glob.glob(os.path.join(directory, '*'))
    target_files = [f for f in all_files if os.path.isfile(f) and f.lower().endswith(ALL_EXTENSIONS)]
    
    print(f"Found {len(target_files)} potential image/vtf files in the directory.")
    
    for face_name, keywords in FACE_KEYWORDS.items():
        found = False
        
        # Check for IMAGE files first
        for ext in IMAGE_EXTENSIONS:
            if found: break
            for fpath in target_files:
                if fpath.lower().endswith(ext):
                    # Check for "skybox" or a similar prefix followed by a keyword
                    fname_lower = os.path.basename(fpath).lower()
                    if any(keyword in fname_lower for keyword in keywords):
                        found_files[face_name] = fpath
                        found = True
                        print(f"Found file for '{face_name}': {os.path.basename(fpath)}")
                        break
        
        # VMT check is kept for error reporting, but not used in stitching
        if not found:
             for fpath in target_files:
                if fpath.lower().endswith(VMT_EXTENSION):
                    fname_lower = os.path.basename(fpath).lower()
                    if any(keyword in fname_lower for keyword in keywords):
                        print(f"ERROR: Found file for '{face_name}' but it is a VMT file: {os.path.basename(fpath)}. An image file (.vtf/.png/etc.) is required.")
                        break

    valid_faces = set(found_files.keys())
    missing_faces = REQUIRED_FACES - valid_faces

    if missing_faces:
        print("\n" + "-" * 50)
        print(f"ATTENTION: The following required skybox faces are missing: {', '.join(sorted(list(missing_faces)))}")
        print("Stitching will fail unless all 6 faces are found.")
        print("-" * 50)
        
    return {face: found_files[face] for face in valid_faces}


def convert_vtf_to_png(vtf_path, output_dir):
    """
    Converts a single VTF file to a PNG file, saving it in the specified output_dir.
    """
    base_name = os.path.basename(vtf_path)
    png_filename = os.path.splitext(base_name)[0] + ".temp_converted.png" 
    png_path = os.path.join(output_dir, png_filename)

    print(f"Converting '{base_name}' to PNG...")

    try:
        parser = Parser(vtf_path)
        image = parser.get_image()
        # Ensure image is in RGBA format before saving
        image = image.convert("RGBA")
        image.save(png_path, "PNG")
        print(f"  -> Saved temporary file: {os.path.basename(png_path)}")
        return png_path
    except Exception as e:
        print(f"Error converting VTF file '{vtf_path}': {e}")
        # Re-raise the exception to stop the stitching process
        raise


def generate_vmat_content_and_save(vmat_path, content, material_type):
    """
    Generates and writes the specified .vmat file content.
    """
    print(f"Creating {material_type} VMAT...")
    
    try:
        with open(vmat_path, 'w') as f:
            f.write(content)
        print(f"SUCCESS: {material_type} VMAT file created at: {os.path.abspath(vmat_path)}")
    except Exception as e:
        print(f"ERROR: Could not write VMAT file to {vmat_path}. Error: {e}")


def create_vmat_file_optionally(skybox_vmat_path, moondome_vmat_path):
    """
    Asks the user which VMAT files they want to create using Y/N prompts.
    """
    print("\n" + "=" * 50)
    print("VMAT Generation Phase")
    print("=" * 50)
    
    saved_count = 0
    
    # --- 1. Standard Skybox VMAT Prompt ---
    try:
        choice_skybox = input("Do you want to create a Skybox Material? (Y/N): ").strip().lower()
        if choice_skybox in ['yes', 'y']:
            generate_vmat_content_and_save(skybox_vmat_path, LDR_VMAT_CONTENT, "Standard Skybox")
            saved_count += 1
        else:
            print("Standard Skybox VMAT creation skipped.")
    except Exception:
        print("Standard Skybox VMAT creation skipped due to input error.")

    # --- 2. Moondome VMAT Prompt ---
    try:
        choice_moondome = input("Do you want to create a Moondome Material? (Y/N): ").strip().lower()
        if choice_moondome in ['yes', 'y']:
            generate_vmat_content_and_save(moondome_vmat_path, MOONDOME_VMAT_CONTENT, "Moondome")
            saved_count += 1
        else:
            print("Moondome VMAT creation skipped.")
    except Exception:
        print("Moondome VMAT creation skipped due to input error.")
        
    print("-" * 50)
    if saved_count > 0:
        print(f"Completed: Created {saved_count} VMAT file(s)".format(saved_count))
    else:
        print("VMAT creation completely skipped.")
    
    print("=" * 50)


def clean_up_vtf_and_vmt(filenames_map, directory):
    """
    Asks the user if they want to delete the original VTF and VMT files used.
    """
    vtf_files_to_delete = []
    
    for face, path in filenames_map.items():
        if path.lower().endswith(('.vtf', '.vmt')): # Include VMTs for cleanup check
            vtf_files_to_delete.append(path)
            
            # If the source was VTF, also check for a paired VMT file
            if path.lower().endswith('.vtf'):
                base_name = os.path.splitext(os.path.basename(path))[0]
                vmt_path = os.path.join(directory, base_name + '.vmt')
                if os.path.exists(vmt_path):
                    vtf_files_to_delete.append(vmt_path)

    vtf_files_to_delete = sorted(list(set(vtf_files_to_delete)))

    if not vtf_files_to_delete:
        print("\nNo original .vtf or associated .vmt files were used/found for cleanup.")
        return

    print("\n" + "=" * 50)
    print("Cleanup Phase: Delete Original Source Files")
    print("=" * 50)
    print("The following original source files were used (or are related VMTs) and can be deleted:")
    for f in vtf_files_to_delete:
        print(f" - {os.path.basename(f)}")

    try:
        choice = input("Do you want to delete source vmt/vtf files? (Y/N): ").strip().lower()
    except Exception:
        print("\nCleanup skipped: Non-interactive session detected or input error.")
        return

    if choice in ['yes', 'y']:
        deleted_count = 0
        for f in vtf_files_to_delete:
            try:
                os.remove(f)
                print(f"   -> Deleted: {os.path.basename(f)}")
                deleted_count += 1
            except OSError as e:
                print(f"   -> ERROR: Could not delete {os.path.basename(f)}. Permission denied or file in use: {e}")
        print(f"\nCleanup complete. {deleted_count} files were deleted.")
    else:
        print("\nCleanup skipped. Original source files were preserved.")
    
    print("=" * 50)


def stitch_cubemap_rotated(filenames_map, output_file_path, temp_dir):
    """
    Performs file conversion, stitching, rotation, and left/right swap.
    """
    print("-" * 50)
    print("Starting Cubemap Rotated Stitcher")
    print("-" * 50)

    if len(filenames_map) != 6:
        # The find_cubemap_files function already prints a detailed warning.
        print("Error: Not all 6 required image files were found. Stitching cancelled.")
        return False

    png_paths_map = {}
    temp_files = []
    
    # Check if the primary input type is EXR (based on the first file)
    # If all files are EXR, use the EXR-specific layout and rotations.
    is_exr_input = all(path.lower().endswith('.exr') for path in filenames_map.values())
    
    print(f"Detected input type: {'EXR (Applying special rotation/swap)' if is_exr_input else 'Standard (Applying default rotation/swap)'}")

    # --- 0. Ensure Output Directory Exists ---
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        print(f"Created output directory: {temp_dir}")

    # --- 1. Conversion Stage (VTF and EXR to temporary PNG) ---
    for face, path in filenames_map.items():
        path_lower = path.lower()
        base_name = os.path.splitext(os.path.basename(path))[0]
        png_filename = base_name + ".temp_converted.png" 
        png_path = os.path.join(temp_dir, png_filename)

        if path_lower.endswith('.vtf'):
            try:
                png_path = convert_vtf_to_png(path, temp_dir) 
                png_paths_map[face] = png_path
                temp_files.append(png_path)
            except Exception:
                for f in temp_files:
                    try: os.remove(f)
                    except: pass
                return False
        
        elif path_lower.endswith('.exr'):
            if not EXR_SUPPORT_ENABLED:
                print(f"\nFATAL ERROR: Cannot convert EXR file '{os.path.basename(path)}'.")
                print("The 'openexr-numpy' library is missing.")
                return False
            
            print(f"Converting '{os.path.basename(path)}' (EXR) to PNG...")
            if convert_exr_to_png(path, png_path):
                png_paths_map[face] = png_path
                temp_files.append(png_path)
                print(f"  -> Saved temporary file: {os.path.basename(png_path)}")
            else:
                print(f"Error converting EXR file '{path}'. Stopping.")
                return False

        else:
            # All other formats (PNG, JPG, TGA, HDR, etc.) are loaded directly by Pillow in step 2
            png_paths_map[face] = path


    # --- 2. Load Images and Determine Face Size ---
    try:
        # Load all images (Pillow will handle the final and temp PNGs)
        images = {}
        for face, path in png_paths_map.items():
            # Pillow handles PNG, JPG, TGA, HDR, and the converted PNGs.
            img = Image.open(path).convert("RGBA")
            images[face] = img

        
        face_width, face_height = images['front'].size
        print(f"\nDetected face size: {face_width}x{face_height}")

        for face, img in images.items():
            w, h = img.size
            if w != face_width or h != face_height:
                print(f"Error: Face '{face}' size mismatch ({w}x{h}). All faces must match ({face_width}x{face_height}).")
                raise ValueError("Image size mismatch.")

    except (FileNotFoundError, ValueError, Exception) as e:
        print(f"An error occurred during image loading/sizing: {e}")
        for f in temp_files:
            try: os.remove(f)
            except: pass
        return False


    # --- 3. Define the new positions and Rotations ---
    # Default S1 to S2 Required Swap (Used for VTF, PNG, JPG, etc.)
    default_layout = {
        'top_slot':    'up',
        'bottom_slot': 'down',
        'left_slot':   'back',  
        'right_slot':  'front', 
        'front_slot':  'right', 
        'back_slot':   'left',  
    }
    
    # EXR Specific Swap (based on user request)
    exr_layout = {
        'top_slot':    'up',
        'bottom_slot': 'down',
        'left_slot':   'back',  # back stays the same (goes to left slot)
        'right_slot':  'left',  # left goes to the place of right
        'front_slot':  'right', # right goes to the place of front
        'back_slot':   'front', # front goes to the place of back
    }
    
    layout_map = exr_layout if is_exr_input else default_layout


    # --- 4. Create the canvas and Paste images ---
    final_width = face_width * 4
    final_height = face_height * 3
    final_image = Image.new('RGBA', (final_width, final_height), (0, 0, 0, 0))

    coords = {
        'top_slot':    (face_width * 1, face_height * 0),
        'left_slot':   (face_width * 0, face_height * 1),
        'front_slot':  (face_width * 1, face_height * 1),
        'right_slot':  (face_width * 2, face_height * 1),
        'back_slot':   (face_width * 3, face_height * 1),
        'bottom_slot': (face_width * 1, face_height * 2),
    }

    print("\nStitching images into the new layout...")
    for slot_name, source_image_name in layout_map.items():
        image_to_paste = images[source_image_name]
        
        # Apply specific rotations ONLY if EXR input is detected
        if is_exr_input:
            rotation_degrees = 0
            if source_image_name in ('front', 'up', 'down'):
                # front one should be rotated 90 degrees
                # top one should be rotated 90 degrees
                # bottom one 90 degrees
                rotation_degrees = -90 # Positive rotation is clockwise, PIL uses negative for clockwise
            elif source_image_name == 'right' and slot_name == 'front_slot':
                # right goes in the place of front and rotates 180 degrees
                rotation_degrees = 180
            elif source_image_name == 'left' and slot_name == 'right_slot':
                # left goes in the place of right and rotates 180 degrees
                rotation_degrees = 180
            elif source_image_name == 'back':
                # back stays the same (no rotation)
                rotation_degrees = 0

            if rotation_degrees != 0:
                # Rotate the image before pasting (expand=False to maintain size)
                image_to_paste = image_to_paste.rotate(rotation_degrees, expand=False)
                print(f"Pasting image from source '{source_image_name}' (Rotated {abs(rotation_degrees)}°) into output '{slot_name}' slot...")
            else:
                print(f"Pasting image from source '{source_image_name}' (No Rotation) into output '{slot_name}' slot...")

        else:
            # Default behavior (no extra rotation/swapping needed beyond the base layout)
            print(f"Pasting image from source '{source_image_name}' into output '{slot_name}' slot at {coords[slot_name]}...")

        position = coords[slot_name]
        final_image.paste(image_to_paste, position)

    # --- 5. Save the final image and Clean up ---
    final_image.save(output_file_path, "PNG")
    print("-" * 50)
    print(f"SUCCESS: Stitched cubemap saved to: {os.path.abspath(output_file_path)}")
    print(f"Final resolution: {final_width}x{final_height}")

    # Clean up temporary files
    for f in temp_files:
        try:
            os.remove(f)
        except OSError as e:
            print(f"Warning: Could not remove temporary file {f}: {e}")

    if temp_files:
        print(f"Cleaned up {len(temp_files)} temporary converted files inside '{temp_dir}'.")
    
    print("-" * 50)

    return True


# ==============================================================================
# SCRIPT EXECUTION
# ==============================================================================

if __name__ == "__main__":
    
    # 1. Find the 6 required cubemap files by keyword
    file_map = find_cubemap_files(INPUT_DIRECTORY)
    
    # 2. Convert and stitch the found files
    success = stitch_cubemap_rotated(file_map, FINAL_OUTPUT_PATH, OUTPUT_DIR)
    
    # 3. Optional VMAT creation after successful stitching
    if success:
        # Calls the function that handles the VMAT choices
        create_vmat_file_optionally(FINAL_SKYBOX_VMAT_PATH, FINAL_MOONDOME_VMAT_PATH)
        
    # 4. Optional VMT/VTF cleanup after VMAT creation
    if success:
        clean_up_vtf_and_vmt(file_map, INPUT_DIRECTORY)
        
    # 5. Final Confirmation and Auto-Exit (Only shows SUCCESS if stitching was successful)
    print("\n" + "#" * 50)
    if success:
        print(f"PROCESS COMPLETE: All output files were created in the '{OUTPUT_DIR}' folder.")
    else:
        print("PROCESS FAILED: Output image creation failed. Check errors and missing files above.")
    print("#" * 50)
        
    print("Closing script in 3 seconds...")
    time.sleep(3)
    sys.exit()