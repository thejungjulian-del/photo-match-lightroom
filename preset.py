"""
preset.py
---------
This file does ONE job: take a bunch of slider numbers (exposure, contrast,
colors, etc.) and turn them into a real Lightroom preset file (.xmp).

A Lightroom preset is just a text file written in a format called XMP.
Lightroom reads attributes that start with "crs:" (Camera Raw Settings).
For example  crs:Contrast2012="20"  means "set the Contrast slider to +20".

So all we do here is plug your numbers into a template. That's it.
"""

import uuid  # used to give each preset a unique ID so Lightroom doesn't confuse it with another


# The 8 colors Lightroom's HSL panel lets you tune, in the exact order/names
# Lightroom expects them.
HSL_COLORS = ["Red", "Orange", "Yellow", "Green", "Aqua", "Blue", "Purple", "Magenta"]


def _num(value, default=0):
    """Safely turn whatever we got into a number. If it's missing/broken, use the default."""
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return default


def build_xmp(values, preset_name="Photo Match"):
    """
    values: a Python dictionary of slider numbers (see app.py for the exact shape).
    preset_name: what the preset will be called inside Lightroom.

    Returns: one big string of text that IS the .xmp preset file.
    """

    basic = values.get("basic", {})
    hsl = values.get("hsl", {})
    grade = values.get("colorGrade", {})

    # --- The "Basic" panel sliders ---------------------------------------
    # Exposure is a decimal (like +0.35). Everything else is a whole number.
    crs = {
        "Exposure2012": f"{_num(basic.get('exposure')):+.2f}",
        "Contrast2012": int(_num(basic.get("contrast"))),
        "Highlights2012": int(_num(basic.get("highlights"))),
        "Shadows2012": int(_num(basic.get("shadows"))),
        "Whites2012": int(_num(basic.get("whites"))),
        "Blacks2012": int(_num(basic.get("blacks"))),
        "Texture": int(_num(basic.get("texture"))),
        "Clarity2012": int(_num(basic.get("clarity"))),
        "Dehaze": int(_num(basic.get("dehaze"))),
        "Vibrance": int(_num(basic.get("vibrance"))),
        "Saturation": int(_num(basic.get("saturation"))),
        # Vignette (the soft darkening at the edges)
        "PostCropVignetteAmount": int(_num(values.get("vignette"))),
    }

    # --- The HSL panel (tune each color's hue / saturation / luminance) ---
    for color in HSL_COLORS:
        c = hsl.get(color.lower(), {})
        crs[f"HueAdjustment{color}"] = int(_num(c.get("h")))
        crs[f"SaturationAdjustment{color}"] = int(_num(c.get("s")))
        crs[f"LuminanceAdjustment{color}"] = int(_num(c.get("l")))

    # --- Color Grading (tints the shadows / midtones / highlights) --------
    crs["ColorGradeShadowHue"] = int(_num(grade.get("shadowHue")))
    crs["ColorGradeShadowSat"] = int(_num(grade.get("shadowSat")))
    crs["ColorGradeMidtoneHue"] = int(_num(grade.get("midtoneHue")))
    crs["ColorGradeMidtoneSat"] = int(_num(grade.get("midtoneSat")))
    crs["ColorGradeHighlightHue"] = int(_num(grade.get("highlightHue")))
    crs["ColorGradeHighlightSat"] = int(_num(grade.get("highlightSat")))

    # Turn our dictionary into lines like:   crs:Contrast2012="20"
    crs_lines = "\n   ".join(f'crs:{key}="{val}"' for key, val in crs.items())

    preset_uuid = str(uuid.uuid4()).replace("-", "").upper()

    # The full preset file. The {placeholders} get filled in by .format() below.
    xmp = f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="Photo Match App">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
   xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
   crs:PresetType="Normal"
   crs:Cluster=""
   crs:UUID="{preset_uuid}"
   crs:SupportsAmount="False"
   crs:SupportsColor="True"
   crs:SupportsMonochrome="True"
   crs:SupportsHighDynamicRange="True"
   crs:SupportsNormalDynamicRange="True"
   crs:SupportsSceneReferred="True"
   crs:SupportsOutputReferred="True"
   crs:CameraModelRestriction=""
   crs:Copyright=""
   crs:ContactInfo=""
   crs:Version="15.4"
   crs:ProcessVersion="11.0"
   crs:HasSettings="True"
   {crs_lines}>
   <crs:Name>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">{preset_name}</rdf:li>
    </rdf:Alt>
   </crs:Name>
   <crs:Group>
    <rdf:Alt>
     <rdf:li xml:lang="x-default">Photo Match App</rdf:li>
    </rdf:Alt>
   </crs:Group>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""
    return xmp
