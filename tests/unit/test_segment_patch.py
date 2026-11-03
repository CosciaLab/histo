"""Tests for bin/segment_patch.py: the image element a spec names and sopa's CLI defaults."""

import pytest
from segment_patch import image_key_for, method_arguments, segmentation_arguments


def test_image_key_full_and_projected():
    attrs = {"cell_segmentation_image": "img"}
    assert image_key_for(attrs, "full") == "img"
    assert image_key_for(attrs, "projected") == "img_projected"


def test_image_key_missing_attribute_names_it():
    with pytest.raises(ValueError, match="cell_segmentation_image"):
        image_key_for({}, "full")


def test_image_key_unknown_image():
    with pytest.raises(ValueError, match="sideways"):
        image_key_for({"cell_segmentation_image": "img"}, "sideways")


def test_cellpose_defaults_are_sopa_cli_defaults():
    spec = {"method": "cellpose", "channels": ["a"], "method_kwargs": {"diameter": 30}}
    kw = method_arguments(spec)
    assert kw["flow_threshold"] == 2
    assert kw["cellprob_threshold"] == -6
    assert kw["model_type"] == "cyto3"
    assert kw["pretrained_model"] is None
    assert kw["gpu"] is False
    assert kw["diameter"] == 30
    assert kw["channels"] == ["a"]


def test_spec_value_overrides_default():
    spec = {"method": "cellpose", "channels": ["a"], "method_kwargs": {"flow_threshold": 0.4}}
    assert method_arguments(spec)["flow_threshold"] == 0.4


def test_instanseg_defaults():
    kw = method_arguments({"method": "instanseg", "channels": None, "method_kwargs": {}})
    assert kw["model_type"] == "fluorescence_nuclei_and_cells"
    assert kw["target"] == "cells"
    assert kw["pixel_size"] is None
    assert "channels" not in kw


def test_unknown_method():
    with pytest.raises(ValueError, match="stardist"):
        method_arguments({"method": "stardist", "method_kwargs": {}})


def test_method_arguments_does_not_mutate_spec():
    spec = {"method": "cellpose", "channels": ["a"], "method_kwargs": {"diameter": 30}}
    method_arguments(spec)
    assert spec["method_kwargs"] == {"diameter": 30}


def test_extra_kwargs_are_parsed_and_merged_flat():
    spec = {
        "method": "cellpose",
        "channels": ["a"],
        "method_kwargs": {"diameter": 30},
        "method_kwargs_extra": "{'niter': 10, 'model_type': 'nuclei'}",
    }
    kw = method_arguments(spec)
    assert kw["niter"] == 10 and kw["model_type"] == "nuclei" and kw["diameter"] == 30


@pytest.mark.parametrize("extra", [None, ""])
def test_no_extra_kwargs(extra):
    spec = {"method": "instanseg", "method_kwargs": {"target": "cells"}, "method_kwargs_extra": extra}
    assert method_arguments(spec)["target"] == "cells"


@pytest.mark.parametrize(
    "method,key",
    [("cellpose", "diameter"), ("cellpose", "channels"), ("cellpose", "gpu"), ("instanseg", "device")],
)
def test_extra_kwarg_colliding_with_an_explicit_one_fails_naming_it(method, key):
    spec = {"method": method, "method_kwargs": {"diameter": 30}, "method_kwargs_extra": f"{{'{key}': 1}}"}
    with pytest.raises(ValueError, match=f"{method}_kwargs key '{key}' collides"):
        method_arguments(spec)


@pytest.mark.parametrize("text", ["[1, 2]", "niter=10", "{'a': open}"])
def test_extra_kwargs_must_be_a_dict_literal(text):
    spec = {"method": "instanseg", "method_kwargs": {}, "method_kwargs_extra": text}
    with pytest.raises(ValueError, match="instanseg_kwargs"):
        method_arguments(spec)


def test_segmentation_defaults_per_method():
    cp = segmentation_arguments({"method": "cellpose"})
    assert cp == {"min_area": 0, "clip_limit": 0.2, "clahe_kernel_size": None, "gaussian_sigma": 1}
    ins = segmentation_arguments({"method": "instanseg", "segmentation_kwargs": {}})
    assert ins == {"min_area": 0, "clip_limit": 0, "clahe_kernel_size": None, "gaussian_sigma": 0}


def test_segmentation_override():
    spec = {"method": "instanseg", "segmentation_kwargs": {"gaussian_sigma": 2, "min_area": 15}}
    kw = segmentation_arguments(spec)
    assert kw["gaussian_sigma"] == 2
    assert kw["min_area"] == 15
    assert kw["clip_limit"] == 0
