# SDMI-Package
### Mongil Stardive Model Importer ALPHA

THIS IS NOT A FULL **MI STYLE PACKAGE

This Mod Loader is just a basic 3DMigoto script on Mongil Stardive for Verna that allows you to use any body mesh you want when the body is <= 16384 verts

There are no Global HLSL shaders/keys/etc, only a basic script to replace Vernas body mesh and some others things.

I made this is a week with AI so this probably isn't the best solution but it's a Proof of Concept that has alot of the basics down so that people can start modding a new game if they want, I might work on this more in the future but I'll see how this works for now. 


### Prerequisites

Open the game and in the settings set your settings to dx11

### How to run the Launcher:

https://github.com/hondaislife420/XXMI-Launcher

Because the Launcher has to be launched with admin privs, so does XXMI, but if you just run 'python app.py' in an admin terminal then it will auto update to the exe version.
You can also try compiling into an exe with pyinstaller but i found it easier using python for testing

1. Double-Click app.py from Explorer in XXMI-Launcher-main\src\xxmi_launcher\app.py
2. Add SDMI to available apps in XXMI then press settings icon.
3. Turn off Auto-Update

After this you can open a Admin Command Prompt:
```
cd C:\Path\To\XXMI-Launcher-main\src\xxmi_launcher\
python app.py
```
Then continue installation as normal


### How to import models:

1. If you want to get a verna obj to edit/compare models to run:
```
cd SDMI\Mods\Verna\Tools
python 1_dump_to_blender.py
```
Then open SDMI\Mods\Verna\Objects and you will see a variety of Verna objects

2. If you want to use a custom model:

- First make sure that all parts you are replacing line up with the verna model that was dumped
- Put it all obj files in one folder then run:
```
cd SDMI\Mods\Verna\Tools
python 2_import_free_n_parts.py C:\Path\To\New\Objs
```
- Make sure you resize/rename and save the dds images to replace in SDMI\Mods\Verna\Textures
- Press F10/Reload and it should be

## Known Bugs:

### SDMI:

- Character menu is disabled because opening that spawns another character and the script takes over both vb0 buffers
- The face is leading infront of the body because the custom script is running later than the games script, this mostly will be fixed once if the face is also replaced with a custom script
- In Verna mod I replace the legs with skin causes the replaced texture to be applied constantly with brown ontop somehow (at least from verna's socks)
- This is only for Verna's body as of now
