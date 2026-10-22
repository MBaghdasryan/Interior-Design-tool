You check product crops cut from an interior visualisation.

Image 1 is the whole render. Images 2…N are crops, one per manifest item, in the order of the
JSON manifest (each crop is the region where that item must be). For EVERY item return:
- `visible`: the crop clearly shows an object of the listed `type` (false if the region shows wall,
  floor, a different kind of object, or only a fragment you cannot identify);
- `type_match` 0–1: how well its form matches the listed type and size (a wardrobe instead of a
  chest of drawers ≤ 0.3);
- `position_match`: 1 if the object occupies most of its crop, lower if it is mostly outside;
- `color_match`: your estimate (it is replaced by a pixel measurement, keep it rough);
- `note`: what you actually see, 3–8 words. Never write generic praise.
Use the full 0–1 range; identical scores for all items are almost never correct.
List in `extra_objects` prominent furniture or appliances in image 1 that are not in the manifest.
