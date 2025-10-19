from PIL import Image
import os
import sys
import glob
import time 
import textwrap
import numpy as np 

# --- PyInstaller Hook for vtf2img ---
# This block ensures native dependencies for vtf2img (like py_vtf) are loaded
if getattr(sys, 'frozen', False):
    try:
        import py_vtf
    except ImportError:
        pass
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

# --- CONFIGURATION (Initial/Default Values) ---
OUTPUT_DIR = "skybox" 
INPUT_DIRECTORY = "." 
# The following will be dynamically set in __main__
FINAL_PREFIX = "skybox_jimi" 
# --- END CONFIGURATION ---

# These variables are now calculated dynamically at the start of the script's execution
FINAL_OUTPUT_FILENAME = f"{FINAL_PREFIX}.png"
FINAL_SKYBOX_VMAT_FILENAME = f"skybox_{FINAL_PREFIX}.vmat"
FINAL_MOONDOME_VMAT_FILENAME = f"moondome_{FINAL_PREFIX}.vmat"

# Path for SkyTexture inside the VMAT (must use engine paths)
SKYTEXTURE_PATH = f"materials/{OUTPUT_DIR}/{FINAL_OUTPUT_FILENAME}"

FINAL_OUTPUT_PATH = os.path.join(OUTPUT_DIR, FINAL_OUTPUT_FILENAME)
FINAL_SKYBOX_VMAT_PATH = os.path.join(OUTPUT_DIR, FINAL_SKYBOX_VMAT_FILENAME)
FINAL_MOONDOME_VMAT_PATH = os.path.join(OUTPUT_DIR, FINAL_MOONDOME_VMAT_FILENAME)


# --- TARGET SLOT DEFINITION (FIXED) ---
TARGET_SLOTS = ['up', 'left', 'front', 'right', 'back', 'down']
# --- END TARGET SLOT DEFINITION ---


# --- CUSTOMIZABLE TRANSFORMATION CONFIGS ---

# Format: 'Target Slot': ('Source Face', Rotation Degrees (CCW), PIL Flip Constant)
# Rotation Degrees (CCW): 90, -90 (CW), 180, 0 (None)
# PIL Flip Constant: None, Image.FLIP_LEFT_RIGHT, Image.FLIP_TOP_BOTTOM, Image.ROTATE_180

# 1. Configuration for EXR files (Customizable for HDR renders)
# --- START CUSTOMIZATION HERE FOR .EXR FILES ---
EXR_TRANSFORMS = {
    # .EXR files are set to no rotation/flip (0, None) by default. 
    # Adjust these values based on your EXR renderer output standard.
    'up':      ('up', -90, None),
    'down':    ('down', -90, None),
    'left':    ('front', 0, None),
    'front': ('right', -90, None),
    'right': ('back', 180, None),
    'back':    ('left', 90, None),
}
# --- END CUSTOMIZATION HERE FOR .EXR FILES ---

# 2. Configuration for all other formats (VTF, PNG, JPG, etc.) - Standard 1:1 Cubemap
# --- CORRECTED STANDARD ROTATIONS FOR NON-EXR FILES (VTF/PNG) ---
DEFAULT_TRANSFORMS = {
    # Standard cubemap projection (VTF/Source) requires a 180-degree rotation on UP/DOWN for 4x3 format.
    # The image file names must match the target slot name.
    'up':      ('up', 0, None),
    'down':    ('down', 0, None),
    'left':    ('back', 0, None), 
    'front':   ('right', 0, None),
    'right':   ('front', 0, None), 
    'back':    ('left', 0, None),
}
# --- END CORRECTED ROTATIONS ---

# 3. Configuration for HL2/TF2 Dome Map files (2:1 aspect ratio on horizontal faces)
# The faces are typically named back, up, rt, ft, lf, dn (or similar).
# They also require rotation correction for the CS:GO/CS2 format.
# The up/down faces often use a 1:1 format, but the others are 2:1.
# This configuration *assumes* the 'up' and 'down' faces are already 1:1 squares
# or will be handled by the 2:1 to 1:1 conversion (which uses only the top half of the 2:1 image).
# If the source is a standard TF2 skybox, the faces are often already in the correct orientation 
# for the 4x3 layout, but require a 180-degree flip on UP/DOWN.
# NOTE: The 2:1 to 1:1 cropping logic is already in place; this transform only needs to handle rotation.
HL2_TF2_DOME_TRANSFORMS = {
    # Typical Source-engine cubemap rotation (up/down flip is required for 4x3 format)
    'up':      ('up', 0, None),
    'down':    ('down', 0, None),
    'left':    ('back', 0, None),
    'front':   ('right', 0, None),
    'right':   ('front', 0, None),
    'back':    ('left', 0, None),
}

# --- VMAT TEMPLATE (LDR Only) ---
def get_ldr_vmat_content(sky_texture_path):
    """Generates the VMAT content with the correct dynamic texture path."""
    return f"""// THIS FILE IS AUTO-GENERATED (STANDARD SKYBOX)

Layer0
{{
    shader "sky.vfx"

    //---- Format ----
    F_TEXTURE_FORMAT2 1 // Dxt1 (LDR)

    //---- Texture ----
    g_flBrightnessExposureBias "0.000"
    g_flRenderOnlyExposureBias "0.000"
    SkyTexture "{sky_texture_path}"


    VariableState
    {{
        "Texture"
        {{
        }}
    }}
}}"""
# --------------------

# --- MOONDOME VMAT TEMPLATE (NEW) ---
def get_moondome_vmat_content(sky_texture_path):
    """Generates the Moondome VMAT content with the correct dynamic texture path."""
    return f"""// THIS FILE IS AUTO-GENERATED (MOONDOME)

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
    TextureCubeMap "{sky_texture_path}"

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

def determine_skybox_prefix(filenames_map):
    """
    Analyzes the found filenames (e.g., 'sky_day01_01up.vtf' or 'sky144bk.vtf') 
    and determines the common prefix (e.g., 'sky_day01_01' or 'sky144').
    
    ***
    CORRECTED LOGIC: Find the keyword, strip it, and then clean up trailing separators ONLY.
    ***
    """
    if not filenames_map:
        return "default_skybox"

    # Keywords to strip from the end of the filename (before extension)
    KEYWORDS = ['up', 'dn', 'bk', 'ft', 'lf', 'rt', 'top', 'down', 'back', 'front', 'left', 'right']
    
    prefixes = []
    
    for face, full_path in filenames_map.items():
        # Get the filename without directory or extension
        filename = os.path.basename(full_path)
        name_no_ext = os.path.splitext(filename)[0].lower()
        
        prefix = name_no_ext
        found_keyword = False
        
        # Strip all keywords from the end
        for keyword in sorted(KEYWORDS, key=len, reverse=True): # Check long keywords first
            if name_no_ext.endswith(keyword):
                # Found the face keyword. Now, strip the keyword.
                temp_prefix = name_no_ext[:-len(keyword)]

                # Clean up any trailing separators (like _, -, or digits) right before the keyword
                # This ensures 'sky144_bk' -> 'sky144' and 'sky144bk' -> 'sky144'
                
                # Strip non-alphanumeric characters or single digits from the end 
                # (to catch 'sky_day01_01_' or 'sky144-')
                
                # Simple cleanup of trailing non-alphanumeric chars
                prefix = temp_prefix.rstrip('_-')
                
                # Check for single-digit suffixes that might be face identifiers (e.g. up1)
                # If the remaining part is only digits, it's safer to keep the last digit if it's the only one.
                # However, for 'sky144bk', we want to keep the '144'. 
                # The simple rstrip('_-') is the most reliable approach for standard naming conventions.
                
                if not prefix: # if stripping resulted in an empty string (e.g., 'up.vtf')
                    prefix = name_no_ext
                    
                found_keyword = True
                break # Exit the keyword loop once the correct keyword is found
        
        if found_keyword and prefix:
            prefixes.append(prefix)
        else:
            # Fallback if no keyword was found (e.g., if the file was just 'sky.png')
            prefixes.append(name_no_ext) 

    # Find the shortest prefix (which is usually the most correct common part)
    if not prefixes:
        return "default_skybox"
        
    final_prefix = min(prefixes, key=len)
    
    # Simple validation that all other prefixes start with the shortest one
    for p in prefixes:
        if not p.startswith(final_prefix):
            print(f"Warning: Filename prefixes are inconsistent. Using '{final_prefix}'.")
            break
            
    return final_prefix

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
                        # Ensure a match on the full word or a common abbreviation
                        for keyword in keywords:
                            # Simple check for keyword at the end of filename (before extension)
                            name_no_ext = os.path.splitext(fname_lower)[0]
                            if name_no_ext.endswith(keyword):
                                found_files[face_name] = fpath
                                found = True
                                print(f"Found file for '{face_name}': {os.path.basename(fpath)}")
                                break
                            
                        if found: break
        
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
        print(f"     -> Saved temporary file: {os.path.basename(png_path)}")
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


def create_vmat_file_optionally(skybox_vmat_path, moondome_vmat_path, sky_texture_path):
    """
    Asks the user which VMAT files they want to create using Y/N prompts, with spacing.
    Now requires the sky_texture_path to generate content dynamically.
    """
    print("\n" + "=" * 50)
    print("VMAT Generation Phase")
    print("=" * 50)
    
    saved_count = 0
    
    # Generate content with the resolved path
    ldr_content = get_ldr_vmat_content(sky_texture_path)
    moondome_content = get_moondome_vmat_content(sky_texture_path)

    # --- 1. Skybox VMAT Prompt ---
    try:
        choice_skybox = input("Do you want to create a Skybox Material? (Y/N): ").strip().lower()
        if choice_skybox in ['yes', 'y']:
            generate_vmat_content_and_save(skybox_vmat_path, ldr_content, "Skybox")
            saved_count += 1
        else:
            print("Skybox VMAT creation skipped.")
    except Exception:
        print("Skybox VMAT creation skipped due to input error.")

    # --- 2. Moondome VMAT Prompt ---
    print("") # Added blank line for spacing
    try:
        choice_moondome = input("Do you want to create a Moondome Material? (Y/N): ").strip().lower()
        if choice_moondome in ['yes', 'y']:
            generate_vmat_content_and_save(moondome_vmat_path, moondome_content, "Moondome")
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
    Asks the user if they want to delete the original source materials (VTF, VMT, EXR, PNG, JPG, etc.) used.
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
        print("\nNo original source materials (.vtf, .png, .exr, etc.) or associated .vmt files were used/found for cleanup.")
        return

    # --- Cleanup Phase Header ---
    print("\n" + "=" * 50)
    print("Cleanup Phase: Delete Source Materials")
    print("=" * 50)
    print("The following original source materials were used and can be deleted:")
    for f in files_to_delete:
        print(f" - {os.path.basename(f)}")

    try:
        # --- Prompt with NEW wording and NO colors ---
        choice = input(
            f"Do you want to remove source materials listed above? "
            f"(Y/N): "
        ).strip().lower()
    except Exception:
        print("\nCleanup skipped: Non-interactive session detected or input error.")
        return

    if choice in ['yes', 'y']:
        deleted_count = 0
        for f in files_to_delete:
            try:
                os.remove(f)
                print(f"     -> Removed: {os.path.basename(f)}")
                deleted_count += 1
            except OSError as e:
                print(f"     -> ERROR: Could not remove {os.path.basename(f)}. Permission denied or file in use: {e}")
        print(f"\nCleanup complete. {deleted_count} source materials were removed.")
    else:
        print("\nCleanup skipped. Original source materials were preserved.")
        
    print("=" * 50)


def stitch_cubemap_rotated(filenames_map, output_file_path, temp_dir):
    """
    Performs file conversion, stitching, and applies source format-specific 
    rotations/placements.
    Supports standard 1:1 faces (CS:GO/CS2) and 2:1 horizontal faces (TF2/HL2).
    """
    print("-" * 50)
    print("Starting Skybox Converter")
    print("-" * 50)

    if len(filenames_map) != 6:
        print("Error: Not all 6 required image files were found. Stitching cancelled.")
        return False

    png_paths_map = {}
    temp_files = []
    face_source_info = {}
    
    # --- 0. Ensure Output Directory Exists ---
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        print(f"Created output directory: {temp_dir}")

    # --- 1. Conversion Stage (VTF and EXR to temporary PNG) ---
    for face, path in filenames_map.items():
        path_lower = path.lower()
        source_format_type = 'default'
        
        if path_lower.endswith('.vtf'):
            try:
                # Use a specific temp name for converted VTF files
                png_path = os.path.join(temp_dir, os.path.splitext(os.path.basename(path))[0] + ".temp_converted.png")
                
                # Use the convert function to get the path
                converted_path = convert_vtf_to_png(path, temp_dir) 
                
                png_paths_map[face] = converted_path
                temp_files.append(converted_path)
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
                print(f"     -> Saved temporary file: {os.path.basename(png_path)}")
            else:
                print(f"Error converting EXR file '{path}'. Stopping.")
                return False

        else:
            # All other formats (PNG, JPG, TGA, HDR, etc.) are loaded directly
            png_paths_map[face] = path
            
        # Store source format type for later use in transformations
        face_source_info[face] = source_format_type


    # --- 2. Load Images and Determine Face Size and Ratio (CORRECTED LOGIC) ---
    try:
        images = {}
        valid_sizes = []
        MIN_SIZE = 64 # Ignore extremely small images (like 4x4 placeholders)

        # Load all images first
        for face, path in png_paths_map.items():
            img = Image.open(path).convert("RGBA")
            images[face] = img
            w, h = img.size
            if w >= MIN_SIZE and h >= MIN_SIZE:
                valid_sizes.append((w, h))

        if not valid_sizes:
            print("Error: Could not find any skybox face larger than 64x64. Check source files.")
            raise ValueError("No valid image size found.")

        # Find the most common/largest size, or just use the largest found size
        face_width, face_height = images['front'].size
        
        # Fallback in case 'front' is also a placeholder
        if face_width < MIN_SIZE or face_height < MIN_SIZE:
            face_width, face_height = max(valid_sizes, key=lambda x: x[0] * x[1])
            print(f"Warning: 'front' face was a placeholder. Using largest face size found: {face_width}x{face_height}")


        print(f"\nDetected base face size: {face_width}x{face_height}")

        # --- Aspect Ratio Check for TF2/HL2 Mode ---
        is_dome_map = False
        ratio = face_width / face_height
        
        if 1.9 < ratio < 2.1: # Allow for float tolerance around 2.0
            is_dome_map = True
            print("💡 Detected 2:1 aspect ratio on base size (TF2/HL2 Dome Map format).")
        elif 0.9 < ratio < 1.1: # Allow for float tolerance around 1.0
            print("Detected 1:1 aspect ratio on faces (CS:GO/CS2 Cube Map format).")
        else:
            print(f"Warning: Unusual aspect ratio ({ratio:.2f}). Proceeding with detected size.")
            

    except (FileNotFoundError, ValueError, Exception) as e:
        print(f"An error occurred during image loading/sizing: {e}")
        for f in temp_files:
            try: os.remove(f)
            except: pass
        return False
        
    # --- Base Unit Size Definition ---
    if is_dome_map:
        base_unit_size = face_height # Face is 2H x H. Base unit is H.
    else:
        base_unit_size = face_width 
    
    # Redefine final image parameters using the 1:1 base unit size.
    final_width = base_unit_size * 4
    final_height = base_unit_size * 3

    # Defines the coordinates of the 6 slots in the final 4x3 image
    COORDS = {
        'up':      (base_unit_size * 1, base_unit_size * 0),
        'left':    (base_unit_size * 0, base_unit_size * 1),
        'front':   (base_unit_size * 1, base_unit_size * 1),
        'right':   (base_unit_size * 2, base_unit_size * 1),
        'back':    (base_unit_size * 3, base_unit_size * 1),
        'down':    (base_unit_size * 1, base_unit_size * 2),
    }

    # Create the empty image matrix (the final image) with black background.
    final_image = Image.new('RGBA', (final_width, final_height), (0, 0, 0, 0))
    print(f"Final stitched cubemap canvas size: {final_width}x{final_height}")

    print("\nStitching images using format-specific rotations and placements...")
    
    # Loop over the TARGET SLOTS 
    for target_slot in TARGET_SLOTS:
        
        # --- Select Transformation Map based on detected source type ---
        transform_map = DEFAULT_TRANSFORMS
        config_name = "DEFAULT_TRANSFORMS"
        source_format = face_source_info.get(target_slot, 'default')

        if source_format == 'exr':
            transform_map = EXR_TRANSFORMS
            config_name = "EXR_TRANSFORMS"
        elif is_dome_map and source_format != 'exr': 
            transform_map = HL2_TF2_DOME_TRANSFORMS
            config_name = "HL2_TF2_DOME_TRANSFORMS"

        # Get the transformation values from the selected map
        source_face, rotation_degrees, flip = transform_map.get(target_slot, (target_slot, 0, None))
        
        image_to_paste = images[source_face] 
        transform_description = []

        # --- 2a. Pre-process and Resize Image for Slot ---
        
        # If the image is a placeholder (4x4), skip rotation/resize but still put a black square in the slot.
        if image_to_paste.size[0] < MIN_SIZE:
             # Create a completely black square of the correct base size (base_unit_size x base_unit_size)
             image_to_paste = Image.new('RGBA', (base_unit_size, base_unit_size), (0, 0, 0, 255))
             transform_description.append("REPLACED 4x4 with Black Square")

        elif is_dome_map and target_slot in ['left', 'front', 'right', 'back']:
            # Dome Map Horizontal Face (2:1 -> W x H) to 1:1 Slot (H x H), with black bottom
            target_height = base_unit_size // 2 
            image_resized = image_to_paste.resize((base_unit_size, target_height), Image.Resampling.LANCZOS)
            final_face = Image.new('RGBA', (base_unit_size, base_unit_size), (0, 0, 0, 255))
            final_face.paste(image_resized, (0, 0))
            image_to_paste = final_face
            
            transform_description.append(f"Dome Map (2:1) to 1:1 Top")
            
        else:
            # Standard resize: Scale any other 1:1 image to the correct 1:1 slot size.
            image_to_paste = image_to_paste.resize((base_unit_size, base_unit_size), Image.Resampling.LANCZOS)
            transform_description.append("Resized to 1:1 Slot")


        # --- 2b. Apply Transformations (Rotation/Flip) ---

        # Apply Rotation
        if rotation_degrees != 0:
            image_to_paste = image_to_paste.rotate(rotation_degrees, expand=False)
            transform_description.append(f"Rotated {rotation_degrees}° CCW")
        
        # Apply Flip/Transpose
        if flip is not None:
            image_to_paste = image_to_paste.transpose(flip)
            transform_description.append(f"Applied Transpose: {str(flip).split('.')[-1]}")
            
        # Log the operation
        desc = f"Source '{source_face}' (Format: {source_format.upper()} - Config: {config_name})"
        if transform_description:
            desc += " (" + ", ".join(transform_description) + ")"
        
        print(f"Pasting {desc} into target '{target_slot}' slot...")

        # --- 2c. Final Paste ---
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
    
    # 2. Determine the dynamic prefix
    DYNAMIC_PREFIX = determine_skybox_prefix(file_map)
    print(f"\n--- Determined Skybox Prefix: '{DYNAMIC_PREFIX}' ---")
    
    # 3. Update all global paths and filenames based on the new prefix
    # Output file paths
    FINAL_OUTPUT_FILENAME = f"{DYNAMIC_PREFIX}.png"
    FINAL_SKYBOX_VMAT_FILENAME = f"skybox_{DYNAMIC_PREFIX}.vmat"
    FINAL_MOONDOME_VMAT_FILENAME = f"moondome_{DYNAMIC_PREFIX}.vmat"
    
    # Engine texture path for VMAT
    SKYTEXTURE_PATH = f"materials/{OUTPUT_DIR}/{FINAL_OUTPUT_FILENAME}"

    FINAL_OUTPUT_PATH = os.path.join(OUTPUT_DIR, FINAL_OUTPUT_FILENAME)
    FINAL_SKYBOX_VMAT_PATH = os.path.join(OUTPUT_DIR, FINAL_SKYBOX_VMAT_FILENAME)
    FINAL_MOONDOME_VMAT_PATH = os.path.join(OUTPUT_DIR, FINAL_MOONDOME_VMAT_FILENAME)
    
    # 4. Convert and stitch the found files
    success = stitch_cubemap_rotated(file_map, FINAL_OUTPUT_PATH, OUTPUT_DIR)
    
    # 5. Optional VMAT creation after successful stitching
    if success:
        # Calls the function that handles the VMAT choices, passing the dynamic path
        create_vmat_file_optionally(FINAL_SKYBOX_VMAT_PATH, FINAL_MOONDOME_VMAT_PATH, SKYTEXTURE_PATH)
        
    # 6. Optional source file cleanup after VMAT creation
    if success:
        clean_up_source_files(file_map, INPUT_DIRECTORY)
        
    # 7. Final Confirmation and Auto-Exit
    print("\n" + "=" * 50)
    if success:
        print(f"PROCESS COMPLETE: All output files were created in the '{OUTPUT_DIR}' folder.")
    else:
        print("PROCESS FAILED: Output image creation failed. Check errors and missing files above.")
    print("=" * 50)
        
    print("Closing script in 3 seconds...")
    time.sleep(3)
    sys.exit()
