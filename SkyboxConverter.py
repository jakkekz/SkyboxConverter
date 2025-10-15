from PIL import Image
import os
import sys
import glob
import time 

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

# --- CONFIGURATION ---
OUTPUT_DIR = "skybox" 
FINAL_OUTPUT_FILENAME = "skybox_jimi.png"
FINAL_VMAT_FILENAME = "skybox_jimi.vmat"
INPUT_DIRECTORY = "." 
# Path for SkyTexture inside the VMAT (must use engine paths)
SKYTEXTURE_PATH = f"materials/{OUTPUT_DIR}/{FINAL_OUTPUT_FILENAME}"
# --- END CONFIGURATION ---

FINAL_OUTPUT_PATH = os.path.join(OUTPUT_DIR, FINAL_OUTPUT_FILENAME)
FINAL_VMAT_PATH = os.path.join(OUTPUT_DIR, FINAL_VMAT_FILENAME)

# --- VMAT TEMPLATE (LDR Only) ---
# HDR logic and template have been removed.
LDR_VMAT_CONTENT = f"""// THIS FILE IS AUTO-GENERATED (LDR ONLY)

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
    IMAGE_EXTENSIONS = ('.vtf', '.png', '.jpg', '.jpeg', '.tga', '.hdr')
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
        image = image.convert("RGBA")
        image.save(png_path, "PNG")
        print(f"  -> Saved temporary file: {os.path.basename(png_path)}")
        return png_path
    except Exception as e:
        print(f"Error converting VTF file '{vtf_path}': {e}")
        raise


def generate_vmat_content_and_save(vmat_path):
    """
    Generates and writes the LDR .vmat file content automatically.
    """
    print("\n" + "=" * 50)
    print("VMAT Generation Phase: Creating LDR Material")
    print("=" * 50)
    
    content = LDR_VMAT_CONTENT # Always use LDR content
    
    try:
        with open(vmat_path, 'w') as f:
            f.write(content)
        print(f"\nSUCCESS: LDR VMAT file created at: {os.path.abspath(vmat_path)}")
        print("NOTE: Ensure this VMAT file is placed in your game's 'materials' folder structure.")
    except Exception as e:
        print(f"\nERROR: Could not write VMAT file to {vmat_path}. Error: {e}")
    
    print("=" * 50)


def create_vmat_file_optionally(vmat_path):
    """
    Asks the user if they want to create a VMAT file, then proceeds.
    """
    print("\n" + "=" * 50)
    print("VMAT Generation Phase: Confirmation")
    print("=" * 50)
    try:
        choice = input("Do you want to create a skybox .vmat file? (Y/N): ").strip().lower()
        if choice in ['yes', 'y']:
            generate_vmat_content_and_save(vmat_path)
        else:
            print("VMAT creation skipped.")
    except Exception:
        print("VMAT creation skipped due to input error.")
    print("=" * 50)


def clean_up_vtf_and_vmt(filenames_map, directory):
    """
    Asks the user if they want to delete the original VTF and VMT files used.
    """
    vtf_files_to_delete = []
    
    for face, path in filenames_map.items():
        if path.lower().endswith('.vtf'):
            vtf_files_to_delete.append(path)
            
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
    Returns True on success, False on failure.
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
    
    # --- 0. Ensure Output Directory Exists ---
    if not os.path.exists(temp_dir):
        os.makedirs(temp_dir)
        print(f"Created output directory: {temp_dir}")

    # --- 1. Conversion Stage (VTF to PNG) ---
    for face, path in filenames_map.items():
        if path.lower().endswith('.vtf'):
            try:
                png_path = convert_vtf_to_png(path, temp_dir) 
                png_paths_map[face] = png_path
                temp_files.append(png_path)
            except Exception:
                for f in temp_files:
                    os.remove(f)
                return False
        else:
            png_paths_map[face] = path


    # --- 2. Load Images and Determine Face Size ---
    try:
        images = {face: Image.open(path).convert("RGBA") for face, path in png_paths_map.items()}
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
            os.remove(f)
        return False


    # --- 3. Define the new positions (Rotated + Left/Right Swapped) ---
    new_layout = {
        'top_slot':    'up',
        'bottom_slot': 'down',
        'left_slot':   'back',  
        'right_slot':  'front', 
        'front_slot':  'right', 
        'back_slot':   'left',  
    }

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

    print("\nStitching images into the new layout (Rotated + Left/Right Swapped)...")
    for slot_name, source_image_name in new_layout.items():
        image_to_paste = images[source_image_name]
        position = coords[slot_name]
        print(f"Pasting image from source '{source_image_name}' into output '{slot_name}' slot at {position}...")
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
        # Calls the function that handles the 'Y/N' choice and now auto-generates LDR VMAT
        create_vmat_file_optionally(FINAL_VMAT_PATH)
        
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
        
    print("Closing in 3 seconds...")
    time.sleep(3)
    sys.exit()