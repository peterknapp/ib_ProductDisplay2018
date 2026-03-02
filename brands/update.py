import json, subprocess
with file("mapping.json", "rb") as f:
    mapping = json.load(f)

for key, image_name in mapping.iteritems():
    subprocess.check_call([
        "curl", 
        "https://staging-api.newyorker.de/public/assets/images/signage-logos/" + image_name,
        "-o", image_name
    ])
