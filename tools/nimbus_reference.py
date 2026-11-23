"""Run upstream Nimbus on the fixture crop to produce the parity reference.

Usage: python -I tools/nimbus_reference.py <fixture_dir> [pixel_size [checkpoint]]
Needs Nimbus-Inference==0.0.5 in a numpy<2 environment (see tools/containers/nimbus/README.md).
Reads image.npy and labels.npy; writes factors.json and reference_scores.csv.
pixel_size 1 (default): magnification = model_magnification = 10, so upstream does no rescaling.
Otherwise magnification = 10 / pixel_size and upstream resizes (int()) itself.
checkpoint "latest" downloads V1.pt; pass "V1.pt" inside the nimbus image (no network).
"""

import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import tifffile
from nimbus_inference.nimbus import Nimbus
from nimbus_inference.utils import MultiplexDataset

CHANNEL_NAMES = ("CD45", "FOXP3")  # image.npy channel order, see make_nimbus_fixture.py


def main(fixture, pixel_size=1.0, checkpoint="latest"):
    fixture = Path(fixture)
    image = np.load(fixture / "image.npy")
    labels = np.load(fixture / "labels.npy")
    with tempfile.TemporaryDirectory() as tmp:
        fov = Path(tmp) / "crop"
        fov.mkdir()
        for name, plane in zip(CHANNEL_NAMES, image, strict=False):
            tifffile.imwrite(fov / f"{name}.tiff", plane)
        tifffile.imwrite(Path(tmp) / "labels.tiff", labels)
        dataset = MultiplexDataset(
            [str(fov)],
            lambda _: str(Path(tmp) / "labels.tiff"),
            suffix=".tiff",
            magnification=10 / pixel_size,
            output_dir=tmp,
        )
        # One FOV, so the factor is deterministic (upstream's subset shuffle is moot).
        dataset.prepare_normalization_dict(n_subset=1, overwrite=True)
        nimbus = Nimbus(
            dataset=dataset,
            output_dir=tmp,
            save_predictions=False,
            batch_size=4,
            test_time_aug=True,
            model_magnification=10,
            device="cpu",
            checkpoint=checkpoint,
        )
        table = nimbus.predict_fovs()
        factors = {k: float(v) for k, v in dataset.normalization_dict.items()}
    (fixture / "factors.json").write_text(json.dumps(factors, indent=2))
    out = table[["label", *CHANNEL_NAMES]].sort_values("label")
    out.to_csv(fixture / "reference_scores.csv", index=False)
    print(f"{len(out)} cells; factors {factors}")


if __name__ == "__main__":
    main(sys.argv[1], *([float(sys.argv[2])] if len(sys.argv) > 2 else []), *sys.argv[3:4])
