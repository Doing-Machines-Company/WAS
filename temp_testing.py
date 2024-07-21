import os

def undo_rename_folders(parent_dir):
    # Change to the parent directory
    os.chdir(parent_dir)

    # Loop through all items in the current directory
    for item in os.listdir():
        # Check if it's a directory
        if os.path.isdir(item):
            # Check if the directory name contains '%' (but not '%2F')
            if '%' in item and '%2F' not in item:
                # Create new name by replacing '%' with '%2F'
                new_name = item.replace('%', '%2F')
                
                # Rename the directory
                os.rename(item, new_name)
                
                print(f"Renamed back: {item} -> {new_name}")

# Specify the parent directory
parent_directory = 'dominos'

# Call the function
undo_rename_folders(parent_directory)