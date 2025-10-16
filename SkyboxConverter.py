from PIL import Image
import os
import sys
import glob
import time 
import textwrap
import numpy as np 

# --- ANSI Color Codes ---
# Added ANSI color codes for terminal output
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    ENDC = '\033[0m' # Ends the color, reverts to terminal default
# --- End Color Codes ---

# --- PyInstaller Hook for vtf2img ---
# This block ensures native dependencies for vtf2img (like py_vtf) are loaded
if getattr(sys, 'frozen', False):
    try:
        import py_vtf
        print("PyInstaller Hook: py_vtf dependency loaded.")
    except ImportError:
        print("PyInstaller Hook: Warning, could not load py_vtf (might be fine if already bundled).")
# -----------------------------------

# --- VTR to Image Conversion Library ---
try:
    from vtf2img import Parser
except ImportError:
    print("Error: The 'vtf2img' library is required for VTF conversion.")
    print("Please install it using: pip install vtf2img")
    sys.exit(1)

# --- Image Stitching Library ---
try:
    Image.new
except NameError:
    print("Error: The 'Pillow' library is required for image stitching.")
    print("Please install it using: pip install Pillow")
    sys.exit(1)

# --- EXR Support Library (Using openexr-numpy) ---
EXR_SUPPORT_ENABLED = False
try:
    from openexr_numpy import imread
    EXR_SUPPORT_ENABLED = True
    print("EXR Support: openexr-numpy is installed and ready for .exr files.")
except ImportError:
    print("Warning: The 'openexr-numpy' or 'numpy' library is not installed. .exr file support is unavailable.")

# --- CONFIGURATION ---
OUTPUT_DIR = "skybox" 
FINAL_OUTPUT_FILENAME = "skybox_jimi.png"
FINAL_SKYBOX_VMAT_FILENAME = "skybox_jimi.vmat"
FINAL_MOONDOME_VMAT_FILENAME = "moondome_jimi.vmat"
INPUT_DIRECTORY = "." 
# Path for SkyTexture inside the VMAT (must use engine paths)
SKYTEXTURE_PATH = f"materials/{OUTPUT_DIR}/{FINAL_OUTPUT_FILENAME}"
# --- END CONFIGURATION ---

FINAL_OUTPUT_PATH = os.path.join(OUTPUT_DIR, FINAL_OUTPUT_FILENAME)
FINAL_SKYBOX_VMAT_PATH = os.path.join(OUTPUT_DIR, FINAL_SKYBOX_VMAT_FILENAME)
FINAL_MOONDOME_VMAT_PATH = os.path.join(OUTPUT_DIR, FINAL_MOONDOME_VMAT_FILENAME)

# --- CUSTOMIZABLE TRANSFORMATION CONFIGS ---

# Format: 'Target Slot': ('Source Face', Rotation Degrees (CCW), PIL Flip Constant)
# Rotation Degrees (CCW): 90, -90 (CW), 180, 0 (None)
# PIL Flip Constant: None, Image.FLIP_LEFT_RIGHT, Image.FLIP_TOP_BOTTOM, Image.ROTATE_180

# 1. Configuration for EXR files (Customizable for HDR renders)
# --- START CUSTOMIZATION HERE FOR .EXR FILES ---
EXR_TRANSFORMS = {
    # .EXR files are set to no rotation/flip (0, None) by default. 
    # Adjust these values based on your EXR renderer output standard.
    'up':     ('up', -90, None),
    'down':   ('down', -90, None),
    'left':   ('front', 0, None),
    'front': ('right', -90, None),
    'right': ('back', 180, None),
    'back':   ('left', 90, None),
}
# --- END CUSTOMIZATION HERE FOR .EXR FILES ---

# 2. Configuration for all other formats (VTF, PNG, JPG, etc.)
# --- RESTORED ORIGINAL ROTATIONS FOR NON-EXR FILES ---
DEFAULT_TRANSFORMS = {
    # Restores the standard engine rotations and flips for LDR/VTF/PNG sources.
    'up':     ('up', 0, None),          # Up face: Rotate 180 (transpose(Image.ROTATE_180))
    'down':   ('down', 0, None),        # Down face: Rotate 180 (transpose(Image.ROTATE_180))
    'left':   ('back', 0, None),        # Left face: Rotate 90 CCW, then flip Top/Bottom
    'front': ('right', 0, None),        # Front face: No rotation/flip
    'right': ('front', 0, None),        # Right face: Rotate 90 CW (-90), then flip Top/Bottom
    'back':   ('left', 0, None),      # Back face: Rotate 180 (transpose(Image.ROTATE_180))
}
# --- END RESTORED ROTATIONS ---

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
            pass
        elif image_float.shape[2] == 3:
            # Add an alpha channel of 1s if only RGB is present
            alpha = np.ones((image_float.shape[0], image_float.shape[1], 1), dtype=image_float.dtype)
            image_float = np.concatenate((image_float, alpha), axis=2)
        else:
            raise ValueError(f"EXR file has unexpected channel count: {image_float.shape[2]}")


        # Perform simple tone-mapping/normalization for LDR PNG (0-255).
        clipped_image = np.clip(image_float, 0.0, 1.0) # Clips to 0-1 range

        # Convert to 8-bit unsigned integer (0-255)
        image_8bit = (clipped_image * 255).astype(np.uint8)

        # Use Pillow to save the 8-bit NumPy array as a PNG
        pil_image = Image.fromarray(image_8bit, 'RGBA')
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
        print(f"   -> Saved temporary file: {os.path.basename(png_path)}")
        return png_path
    except Exception as e:
        # Check for the specific error related to format 3 to give a helpful message
        if "Unknown image format 3" in str(e):
             print(f"\nFATAL VTF ERROR: Failed to convert '{base_name}'.")
             print("This VTF uses a rare compression format (Type 3) that is not supported by the Python library.")
             print("Please use VTFEdit to manually export this specific file to PNG/TGA before running the script.")
             raise
        
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
        # Note: No color changes here as the request was only for the 'delete' prompt
        choice_skybox = input("Do you want to create a Standard Skybox Material? (Y/N): ").strip().lower()
        if choice_skybox in ['yes', 'y']:
            generate_vmat_content_and_save(skybox_vmat_path, LDR_VMAT_CONTENT, "Standard Skybox")
            saved_count += 1
        else:
            print("Standard Skybox VMAT creation skipped.")
    except Exception:
        print("Standard Skybox VMAT creation skipped due to input error.")

    # --- 2. Moondome VMAT Prompt ---
    try:
        # Note: No color changes here as the request was only for the 'delete' prompt
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
        print(f"Completed: Created {saved_count} VMAT file(s)")
    else:
        print("VMAT creation completely skipped.")
    
    print("=" * 50)


def clean_up_source_files(filenames_map, directory):
    """
    Asks the user if they want to delete the original source files (VTF, VMT, EXR, PNG, JPG, etc.) used.
    
    APPLYING COLORS HERE:
    - 'delete' text is red
    - 'Y' is green
    - 'N' is red
    """
    files_to_delete = []
    
    IMAGE_SOURCE_EXTENSIONS = ('.vtf', '.png', '.jpg', '.jpeg', '.tga', '.hdr', '.exr') 

    for face, path in filenames_map.items():
        path_lower = path.lower()
        
        # 1. Add all original image files
        if path_lower.endswith(IMAGE_SOURCE_EXTENSIONS):
            files_to_delete.append(path)
            
        # 2. Add associated VMT files if the source was VTF
        if path_lower.endswith('.vtf'):
            base_name = os.path.splitext(os.path.basename(path))[0]
            vmt_path = os.path.join(directory, base_name + '.vmt')
            if os.path.exists(vmt_path):
                files_to_delete.append(vmt_path)

    files_to_delete = sorted(list(set(files_to_delete)))

    if not files_to_delete:
        print("\nNo original source image (.vtf, .png, .exr, etc.) or associated .vmt files were used/found for cleanup.")
        return

    # --- Applying Colors to Section Header ---
    print("\n" + "=" * 50)
    print(f"Cleanup Phase: {Colors.RED}Delete{Colors.ENDC} Original Source Files")
    print("=" * 50)
    print("The following original source files were used and can be deleted:")
    for f in files_to_delete:
        print(f" - {os.path.basename(f)}")

    try:
        # --- Applying Colors to Prompt ---
        choice = input(
            f"Do you want to {Colors.RED}delete{Colors.ENDC} ALL the source files listed above? "
            f"({Colors.GREEN}Y{Colors.ENDC}/{Colors.RED}N{Colors.ENDC}): "
        ).strip().lower()
    except Exception:
        print("\nCleanup skipped: Non-interactive session detected or input error.")
        return

    if choice in ['yes', 'y']:
        deleted_count = 0
        for f in files_to_delete:
            try:
                os.remove(f)
                print(f"     -> Deleted: {os.path.basename(f)}")
                deleted_count += 1
            except OSError as e:
                print(f"     -> ERROR: Could not delete {os.path.basename(f)}. Permission denied or file in use: {e}")
        print(f"\nCleanup complete. {deleted_count} files were deleted.")
    else:
        print("\nCleanup skipped. Original source files were preserved.")
    
    print("=" * 50)


def stitch_cubemap_rotated(filenames_map, output_file_path, temp_dir):
    """
    Performs file conversion, stitching, and applies source format-specific 
    rotations/placements based on the EXR_TRANSFORMS and DEFAULT_TRANSFORMS configs.
    """
    print("-" * 50)
    print("Starting Cubemap Stitcher")
    print("-" * 50)

    if len(filenames_map) != 6:
        print("Error: Not all 6 required image files were found. Stitching cancelled.")
        return False

    png_paths_map = {}
    temp_files = []
    # New: Store the source format for conditional transformation later
    face_source_info = {}
    
    # --- 0. Ensure Output Directory Exists ---
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        print(f"Created output directory: {temp_dir}")

    # --- 1. Conversion Stage (VTF and EXR to temporary PNG) ---
    for face, path in filenames_map.items():
        path_lower = path.lower()
        
        # Determine the source format type
        source_format_type = 'default'
        
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
            source_format_type = 'exr'
            if not EXR_SUPPORT_ENABLED:
                print(f"\nFATAL ERROR: Cannot convert EXR file '{os.path.basename(path)}'.")
                print("The 'openexr-numpy' library is missing.")
                return False
            
            base_name = os.path.splitext(os.path.basename(path))[0]
            png_filename = base_name + ".temp_converted.png" 
            png_path = os.path.join(temp_dir, png_filename)

            print(f"Converting '{os.path.basename(path)}' (EXR) to PNG...")
            if convert_exr_to_png(path, png_path):
                png_paths_map[face] = png_path
                temp_files.append(png_path)
                print(f"   -> Saved temporary file: {os.path.basename(png_path)}")
            else:
                print(f"Error converting EXR file '{path}'. Stopping.")
                return False

        else:
            # All other formats (PNG, JPG, TGA, HDR, etc.) are loaded directly
            png_paths_map[face] = path
            
        # Store source format type for later use in transformations
        face_source_info[face] = source_format_type


    # --- 2. Load Images and Determine Face Size ---
    try:
        images = {}
        for face, path in png_paths_map.items():
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

    
    # --- 3. Define the Global Slot Coordinates ---

    # Defines the coordinates of the 6 slots in the final 4x3 image
    COORDS = {
        'up':    (face_width * 1, face_height * 0),
        'left':  (face_width * 0, face_height * 1),
        'front': (face_width * 1, face_height * 1),
        'right': (face_width * 2, face_height * 1),
        'back':  (face_width * 3, face_height * 1),
        'down':  (face_width * 1, face_height * 2),
    }
    
    # The list of target slots in the final image
    TARGET_SLOTS = ['up', 'down', 'left', 'front', 'right', 'back']


    # --- 4. Create the final image and Paste images ---
    final_width = face_width * 4
    final_height = face_height * 3
    
    # Create the empty image matrix (the final image)
    final_image = Image.new('RGBA', (final_width, final_height), (0, 0, 0, 0))

    print("\nStitching images using format-specific rotations and placements...")
    
    # Loop over the TARGET SLOTS 
    for target_slot in TARGET_SLOTS:
        # Determine which set of transforms to use based on the source image format
        # We assume the Source Face name is the same as the Target Slot name unless explicitly overridden in the config maps.
        
        # Check the source format of the image that would normally be in this slot (target_slot)
        source_format = face_source_info.get(target_slot, 'default')

        if source_format == 'exr':
            transform_map = EXR_TRANSFORMS
            config_name = "EXR_TRANSFORMS"
        else:
            transform_map = DEFAULT_TRANSFORMS
            config_name = "DEFAULT_TRANSFORMS"
            
        # Get the specific transformation rule for this target slot
        # Format: (Source Face, Rotation Degrees CCW, PIL Flip Constant)
        source_face, rotation_degrees, flip = transform_map.get(
            target_slot, 
            (target_slot, 0, None) # Fallback to no change if slot missing from map
        )
        
        # Get the actual image object based on the SOURCE FACE name (which might be swapped)
        image_to_paste = images[source_face] 
        
        transform_description = []

        # Apply Rotation
        if rotation_degrees != 0:
            image_to_paste = image_to_paste.rotate(rotation_degrees, expand=False)
            transform_description.append(f"Rotated {rotation_degrees}° CCW")
        
        # Apply Flip/Transpose
        if flip == Image.FLIP_LEFT_RIGHT:
            image_to_paste = image_to_paste.transpose(Image.FLIP_LEFT_RIGHT)
            transform_description.append("Flipped Left/Right")
        elif flip == Image.FLIP_TOP_BOTTOM:
            image_to_paste = image_to_paste.transpose(Image.FLIP_TOP_BOTTOM)
            transform_description.append("Flipped Top/Bottom")
        elif flip == Image.ROTATE_180:
            image_to_paste = image_to_paste.transpose(Image.ROTATE_180)
            transform_description.append("Rotated 180°")
        elif flip is not None:
             transform_description.append(f"Applied Custom Transpose: {flip}")

        # Log the operation
        desc = f"Source '{source_face}' (Format: {source_format.upper()} - Config: {config_name})"
        if transform_description:
            desc += " (" + ", ".join(transform_description) + ")"
        
        print(f"Pasting {desc} into target '{target_slot}' slot...")

        position = COORDS[target_slot]
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
        
    # 4. Optional source file cleanup after VMAT creation
    if success:
        # Renamed to include all source image types
        clean_up_source_files(file_map, INPUT_DIRECTORY)
        
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