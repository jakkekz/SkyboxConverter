# PyInstaller Hook for Pillow (PIL)
from PyInstaller.utils.hooks import collect_data_files

# This collects all data files (like C libraries and support files) 
# that Pillow relies on and ensures they are bundled.
datas = collect_data_files('PIL')