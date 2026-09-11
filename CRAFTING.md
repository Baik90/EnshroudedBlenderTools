# Custom crafting (0.25.0)

In New Recipe select Equipment, load bases, and choose a weapon resolved through
`visualEntity.ModelResource`. Export Source selects the edited mesh or collection.
The exporter clones the item and visual template, preserving weapon properties;
the cloned template receives the custom RenderModel.

Load Crafting Choices, select a `Workshop / Recipe Template`, add ingredients
using the searchable item catalog, and set Output Count. Equipment always uses
these custom recipe settings. Placeables can opt in with Custom Recipe.

The donor recipe determines the workstation/NPC and crafting menu location.
Additional donor requirements (crafting props, level, duration, etc.) are retained;
knowledge unlocking follows the existing always-known recipe behavior. Ingredients
and outputs are replaced completely. Choose a simple donor for the initial test.
Names in the catalog are internal game debug names.

The exported crafting.json records the selected donor, ingredients and count.
Equipment without a unique direct ModelResource in its visual template is rejected.
Changing attack properties, skinning, and exporting direct clothing models as new
equipment are not covered by this path.

Verified: current archive catalog, Blender registration, generated Lua assertions.
In-game crafting and equipped weapon appearance still require verification.
