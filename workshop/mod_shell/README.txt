Workshop mod shell - notes (this folder ships NO game data and NO generated breeds)

A Workshop upload for Armory is only a thin, data-only shell. The real work is done by the separate Armory app.

Layout of the shell (created by the packaging step, not stored here):

  mod.info                  name, description, version (a short text file in the game's usual mod.info format)
  resource/                 intentionally empty or a placeholder .pak with no entries
  localizations/            intentionally empty

Rules:
- No DLLs, executables or scripts. Data only.
- Do not include generated breeds (arm_<hash>), copies of game files, or anything copied from the game or other mods.
  Generated breeds are created on the player's PC by Armory and written to the game's mods folder as `armory_breeds`.
- The shell must not use the same folder name as the generated mod (`armory_breeds`) to avoid two mods fighting over it.
- Description text lives in ../description.bbcode and must say the editor app is a separate download.
- The shell's mod.info should be written to match the game's current mod.info format by checking an existing mod
  in your own install before uploading; this repository does not ship a template taken from the game.
- Nothing here has been uploaded. Uploading is a manual step by the project owner.
