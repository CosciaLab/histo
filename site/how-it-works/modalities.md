# Caveats by modality

Pitfalls grouped by the kind of data you bring. Each bullet points to the page that explains it.

## Cyclic mIF

- **Cells are lost between cycles.** Later cycles show fewer cells, so the nuclear channel used
  for segmentation is the first `dna` channel, the Ashlar reference. See
  [Channel projection](projection.md).
- **Check the nuclear stain across cycles.** The QC report compares the first and last cycle's
  nuclear stain per cell, which shows cell loss and photobleaching; see [QC report](qc-report.md).
- **Every cycle needs a `dna` channel.** Registration, segmentation and the cross-cycle check
  all read it; see [Inputs](../reference/usage.md#inputs).
- **A poor registration does not stop the run.** Check the report's "Stitching and registration"
  section; see [Ashlar](ashlar.md).

% source: docs/decisions.md#channel-projection
% source: docs/output.md#qc-report
% source: docs/usage.md#inputs
% source: docs/usage.md#when-stitching-or-registration-looks-wrong

## TMA

- **Each core runs the downstream half alone**, then the cores are merged per slide at the end.
  See [TMA dearray](coreograph.md) and [SpatialData](spatialdata.md).
- **Core detection depends on the downsample factor.** The pipeline sweeps factors 3 to 7 against
  your expected core count and diameter; a wrong factor fails silently, so check the TMA map. See
  [TMA dearray](../reference/usage.md#tma-dearray).
- **An unreadable core, or a core whose segmentation is empty, stops the slide.** It is a hard
  failure, not a skipped core; see [Tiled segmentation](tiling.md).
- **Registration is per slide.** Ashlar runs before dearraying, so one failure loses every core,
  and the stitching QC is on the slide report, not the cores; see [Ashlar](ashlar.md).

% source: docs/decisions.md#the-tma-path
% source: docs/usage.md#tma-dearray
% source: docs/decisions.md#segmentation
% source: docs/output.md#qc-report
% source: site/how-it-works/ashlar.md#caveats

## Whole-slide images

- **Segmentation is tiled, so size is not the limit.** Patch width is not set for you; aim for
  16 to 200 patches. See [Choosing `patch_width_pixel`](../reference/usage.md#choosing-patch-width-pixel).
- **Large empty areas can be skipped** with `use_tissue_segmentation`, which is off by default.
  It can find no tissue, which leaves 0 patches and stops the run. See
  [Tiled segmentation](tiling.md).
- **Background subtraction is optional** and can be done after quantification instead; see
  [backsub](backsub.md).
- **Memory follows channels times patch area** for InstanSeg; see [InstanSeg](instanseg.md).

% source: docs/decisions.md#architecture
% source: docs/usage.md#choosing-patch_width_pixel
% source: site/how-it-works/tiling.md#caveats
% source: site/how-it-works/backsub.md#caveats
% source: docs/decisions.md#parameters

## Pixel size

- **It stays in the OME-TIFF.** The store holds pixels, so areas are px² and you convert with
  the pixel size in the stitched OME-TIFF; see [Quantification](quantification.md).
- **The Coreograph sweep reads it from the image's OME-XML.** Without it the sweep stops and
  asks for `coreograph_args`; see [TMA dearray](coreograph.md).
- **InstanSeg needs `instanseg_pixel_size`.** It does not read it from the image; without it the
  pipeline stops at startup. See [InstanSeg](instanseg.md).

% source: docs/decisions.md#pixel-size
% source: docs/decisions.md#quantification
% source: site/how-it-works/coreograph.md#in-this-pipeline
% source: site/how-it-works/instanseg.md#caveats

## H&E

- **Not supported.** H&E is planned; only mIF `ome_tif` input works today. See the
  [README](https://github.com/CosciaLab/histo#readme).

% source: README.md:5
% source: CHANGELOG.md:470
% source: ROADMAP.md:130
