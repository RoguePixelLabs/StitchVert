# StitchVert

Download the Windows x64 installer from [GitHub Releases](https://github.com/RoguePixelLabs/StitchVert/releases). Setup installs StitchVert for the current user and includes Python and Tk. To run from source on Windows, use **Launch StitchVert.cmd** or run `python app.pyw` with Python 3.10 or later and Tkinter.

Use **Help → Check for updates** to compare the installed version with the latest stable GitHub release. If a newer version is available, StitchVert can open the release page so you can download and run the installer. Conversion and previews work offline.

1. Open an embroidery file. The preview shows the full design and the thread list shows the colors in sew order.
2. Select a thread and click **Change color**, or double-click its row. Use **Reset colors** to restore the palette from when you opened the file. Files without thread RGB values start with assigned preview colors.
3. Click **Play** to draw the stitches in order. Use **Pause**, **Resume**, **Replay**, and **Stitches/min** to control playback. Drag the timeline to move to any stitch, including the beginning. Click **Stop** to end playback and show the full design. Playback defaults to 6,000 stitches per minute and can run up to 60,000.
4. Scroll the mouse wheel over the preview to zoom around the pointer. Use **+** and **−** to zoom around the center, drag with the left or middle mouse button to pan, and use **Fit** to center the full design.
5. Click **Print preview** (Ctrl+P) to open a worksheet in your default browser. The worksheet includes design dimensions, the stitch diagram, and thread sections in sewing order. Select Letter or A4 and choose Fit worksheet or Actual size. To preserve actual size, print at 100% on the selected paper size. Use **Print / Save as PDF** to open the browser's print dialog.
6. Select an output format and click **Export**. The app displays how the selected format handles thread colors.

## Format coverage

| Capability | Formats |
| --- | --- |
| Read and write | DSB, DST, DSZ, EXP, GCODE, HUS, JEF, PEC, PES, SEW, T01, TAP, TBF, U01, VIP, VP3, XXX |
| Read | 100, 10O, BRO, DAT, EMD, EXY, FXY, GT, INB, JPX, KSM, MAX, MIT, NEW, PCD, PCM, PCQ, PCS, PHB, PHC, SHV, SPX, STC, STX, ZHS, ZXY |
| Store edited RGB values | PES v6, VIP, VP3, XXX, TBF, GCODE thread comments |
| Map edited colors to a fixed palette | HUS, JEF, PEC, SEW |
| Store thread changes or needle assignments | DSB, standard DST, DSZ, EXP, T01, TAP, U01 |

The preview plays the loaded design at the selected stitch rate. Machine-specific delays, hoop limits, and commands that change during export are outside the simulation. The app writes embroidery designs. PMV sewing-machine motifs and separate color sidecars are outside the file picker.

StitchVert bundles [pyembroidery 1.5.1](https://github.com/EmbroidePy/pyembroidery/tree/1.5.1), with an additional truncation check for XXX records. Its license is in `pyembroidery/LICENSE.txt`.

The additional codecs are implemented in Python and use the bundled encoder. The VIP color table and several format layouts use [libembroidery](https://github.com/Embroidermodder/libembroidery) as a reference. The zlib/libpng license is in `LIBEMBROIDERY-LICENSE.txt`.

TAP output is the stitch stream. Happy workflows requiring a separate MON header need that file from another tool. HUS and VIP are limited to 24 thread sections. HUS, SEW, and VIP exports reject standalone stops that the exporter cannot preserve. JEF+ and U03 are unavailable. PCD, PCQ, and PCS remain import-only because the reference implementations disagree on coordinate scaling.

The seven additional export formats were checked by reopening generated files and comparing the stitch count, sew order, and coordinates. Physical machine compatibility has not been verified.

## Build the Windows installer

Install 64-bit CPython with Tk and Inno Setup 6. Run:

```powershell
.\installeruild.ps1 -InnoCompiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

The installer and its SHA-256 checksum are written to `dist`. Release versions are set in `updates.py`. Publish the corresponding `vMAJOR.MINOR.PATCH` tag as a stable GitHub release with both files.

StitchVert is MIT licensed. See `LICENSE` and the included third-party notices.
