# The store a driver saves

Every capture a ZMART driver saves is one OME-Zarr store: its pixels, and everything that
says how they were made. This page is the agreement every driver writes to and every
reader reads from. It is the same for every microscope.

## Contents

1. [Four layers](#1-four-layers)
2. [The layout](#2-the-layout)
3. [Layer 1: OME-Zarr 0.5](#3-layer-1-ome-zarr-05)
4. [Layer 2: the OME data model](#4-layer-2-the-ome-data-model)
5. [Layer 3: ZMART's annotations](#5-layer-3-zmarts-annotations)
6. [Layer 4: the vendor's description](#6-layer-4-the-vendors-description)
7. [Reading a store](#7-reading-a-store)
8. [Versions](#8-versions)

## 1) Four layers

| Layer | What it is | Where |
|---|---|---|
| 1 | [OME-Zarr 0.5](https://ngff.openmicroscopy.org/0.5/) | `zarr.json` |
| 2 | The [OME data model](https://www.openmicroscopy.org/Schemas/OME/2016-06/), 2016-06, the same as OME-TIFF | `OME/METADATA.ome.xml` |
| 3 | ZMART's annotations | in that XML |
| 4 | The vendor's own description | in that XML |

A fact goes into the first layer that has a place for it. Layers 3 and 4 also keep whole
records (the controller's state, the vendor's description) that repeat some facts of
layers 1 and 2; a reader takes a fact from the lowest layer that has it, and treats
layers 3 and 4 as records.

Layer 3 holds what neither standard knows, and only what the controller's contract
itself defines (`get_state`, `get_xyz`, `acquire`), so it fits every microscope and leans
on none. How a driver arrives at its numbers (an origin, a calibration, which drives it
adds up) is the driver's own: it goes in the driver's `observed` state or in layer 4. Like the controller, its shape is the same for every microscope and
its contents are each microscope's own: the namespaces, the keys of the capture record
and the image frame, and the structure (`changeable` and `observed`,
`actuator_readings` and `used_actuator`) are fixed; what is inside `changeable`,
`observed` and `actuator_readings`, such as a setting or an actuator name, is the
driver's. Layer 4 holds the vendor's words.

A reader in ZMART depends on layers 1 to 3, and on the fixed parts of layer 3 only. It
may show what is inside a state, or hand a saved state back to the same driver
(`set_state`), but never depends on one driver's keys.

**Who reads what, today.** Layer 1 is read by ZMART and by napari (ome-zarr-py). Layers 2
to 4 are read by ZMART. Fiji and OMERO read OME-Zarr through Bio-Formats, whose OME-Zarr
reader (OMEZarrReader 0.6.0) reads Zarr v2 only, so not OME-Zarr 0.5; when it does, the
XML is where OME-Zarr's `bioformats2raw.layout` keeps it (see 2).

## 2) The layout

```
<name>.ome.zarr/
  zarr.json            the image: layer 1, and the store's version
  0/                   its pixels
  OME/
    METADATA.ome.xml   layers 2 to 4
```

`zarr.json`'s attributes:

```json
{"ome": {"version": "0.5", "multiscales": [...], "omero": {...}}, "zmart": {"store": "1"}}
```

The store's root is the image, so every OME-Zarr reader opens it as it is.
`OME/METADATA.ome.xml` is where OME-Zarr's `bioformats2raw.layout` keeps OME-XML; that
layout also moves the image to `0/`, and today it makes napari find nothing at the store
while Fiji and OMERO cannot read OME-Zarr 0.5 either way. When a reader of the XML needs
it, stores move to that layout with one script.

One store holds one position. A projection is a store of its own, in the same layout.

## 3) Layer 1: OME-Zarr 0.5

Under `ome` in `zarr.json`:

- `multiscales`: one, with axes `t` (second), `c`, `z`, `y`, `x` (micrometer), and per
  level a `scale` then a `translation`, both in those units.
  - `scale`: the pixel size. A single plane has no measured z size: its z scale is 1, and
    `metadata` says so.
  - `translation`: the centre of the first voxel, as a position (see 5.3). z grows with
    the index: planes are stored lowest first, so the z scale stays positive.
  - `name`: the image's name. `metadata`: what the levels are. `type`: how a level was
    downsampled, only when there is more than one.
- `omero`: per channel `label`, `color`, `window`, `active`, `coefficient`, `family`,
  `inverted`; and `rdefs` (`defaultT`, `defaultZ`, `model`).

## 4) Layer 2: the OME data model

`OME/METADATA.ome.xml`, schema 2016-06, valid against it, with `<MetadataOnly/>` (the
pixels are in the store) and one `Image`. Everything the model has a field for goes in it,
in its own units:

- `Instrument`: the microscope, objectives, light sources with their power, detectors,
  filters.
- `Image`: `Name`; `AcquisitionDate`; `Description` (what the vendor calls the image),
  right after `AcquisitionDate`; `StageLabel` with the `position_label` `acquire` was given.
- `Pixels` and `Channel`: sizes, pixel size, per channel the name, wavelengths, light
  source settings (attenuation), detector settings (gain, offset), pinhole.
- `Plane`: per plane `TheT`, `TheC`, `TheZ`; `DeltaT`, counted from the capture record's
  `started`; `PositionX` and `PositionY`, the centre of the field of view, and
  `PositionZ`, the plane's z, as positions (see 5.3).

A driver translates its vendor's words into these fields wherever it can.

## 5) Layer 3: ZMART's annotations

In the XML's `StructuredAnnotations`. Each has a namespace under
`https://github.com/ZMB-UZH/ZMART-controller/the_store/1/`, there is one of each, and it is
referenced from the `Image` (the actuator readings from their `Plane`s). A reader finds an
annotation by its namespace, through the `AnnotationRef`s, never by its `ID`.

### 5.1) The controller state — `…/controller-state`

A `CommentAnnotation` holding, as JSON, `get_state()`'s output at the capture, whole:
`changeable` and `observed`.

### 5.2) The capture record — `…/capture-record`

A `CommentAnnotation` holding, as JSON:

| Key | What |
|---|---|
| `position_label`, `acquisition_type` | as `acquire` was given them |
| `acquisition_settings` | `{"asked": ..., "used": ...}`: as `acquire` was given them, and with the `active` value of `get_acquisition_settings` filled in for every setting left out |
| `started`, `finished` | when the capture began and ended, ISO 8601, UTC |
| `xyz` | `get_xyz()`'s output when the capture began |
| `driver` | `{"name": ..., "version": ...}` |
| `controller` | `{"version": ...}` |
| `derived_from` | for a projection: `{"store": <relative path>, "operation": "max over z"}`; absent otherwise |

### 5.3) The image frame — `…/image-frame`

How the stored image relates to what the microscope scanned. A `MapAnnotation`:

| Key | What |
|---|---|
| `pixels` | the 2×2 matrix, as JSON `[[a, b], [c, d]]`, that took the scanned (x, y) to the stored (x, y), acting on a column vector: identity, a turn, or a mirror. It is already applied, so the stored image's axes are the position's axes; a reader never applies it again |

Positions are `get_xyz`'s `position`, in µm. How a driver makes them from its actuator
readings is its own, and said in its `observed` state or in layer 4; the readings
themselves are in 5.4.

### 5.4) The actuator readings — `…/actuator-readings`

Per plane position (per `t` and `z`; the channels share it), a `MapAnnotation` referenced
from those `Plane`s: each actuator's reading, as `get_xyz` names them in
`actuator_readings`, and the `used_actuator` per axis.

## 6) Layer 4: the vendor's description

What the vendor's software says about the image, whole: an `XMLAnnotation` whose root
element carries `xmlns=""` (or the vendor's own namespace), so its element names cannot be
taken for OME's, with no XML declaration inside; or a `CommentAnnotation` when it is not
XML. Its namespace is `https://github.com/ZMB-UZH/ZMART-controller/the_store/1/vendor/<name>`,
named after the vendor's software. The same content, not the same bytes: an XML parser may
write it differently. A readable key–value list of it, and anything else that is the
driver's own (a route, its timing), may go beside it in the same namespace. Nothing in
ZMART reads layer 4; it is there so nothing the vendor knew is lost.

## 7) Reading a store

- Open the store's root: it is the image.
- Take what you need from the store, and hand nothing alongside but its path: the pixel
  size, where the image lies, z, the channels and the time from layer 1; the rest from
  layers 2 and 3. A single plane's z scale says nothing (see 3).
- Never read layer 4, and never depend on what is inside a driver's state or on its
  actuator names.

## 8) Versions

This agreement will change as we learn, and OME-Zarr's own way of keeping OME-XML is
still settling. So the agreement has a version, and every store says which one it was
written to: `"zmart": {"store": "1"}` in `zarr.json`, and the version in the namespaces of
layers 3 and 4, which travel with the XML wherever it goes.

- A key added to layer 3 keeps the version: a reader ignores what it does not know.
- A key changed or removed, or a new layout, is a new version. Readers read every version
  still in use, and refuse one they do not know.
- Nothing is lost between versions: every store keeps the vendor's whole description and
  the whole controller state, so an older store can be rewritten to a newer version.

Version 1 is this page.
