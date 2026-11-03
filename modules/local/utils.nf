// Function library vendored from nf-core/sopa at c2b4e5f. New sopa params go in extractSubArgs() or segmentationSpecs().
// Kept flat despite lint (local_component_structure): as utils/main.nf it fails the stub/versions hooks.

def stringifyItem(String key, value) {
    key = key.replace('_', '-')

    def option = "--${key}"

    if (value instanceof Boolean) {
        return value ? option : "--no-${key}"
    }
    if (value instanceof List) {
        return value.collect { v -> "${option} ${stringifyValueForCli(v)}" }.join(" ")
    }
    if (value instanceof Map) {
        return "${option} \"" + stringifyValueForCli(value) + "\""
    }
    return "${option} ${stringifyValueForCli(value)}"
}

def stringifyValueForCli(value) {
    if (value instanceof Map) {
        return "{" + value.collect { k, v -> "'${k}': ${stringifyValueForCli(v)}" }.join(", ") + "}"
    }
    if (value instanceof List) {
        return "[" + value.collect { stringifyValueForCli(it) }.join(", ") + "]"
    }
    if (value instanceof String) {
        return "'${value}'"
    }
    if (value instanceof Boolean) {
        return value ? "True" : "False"
    }
    if (value instanceof Number) {
        return value.toString()
    }
    return "'${value.toString()}'"
}

def extractSubArgs(Map args, String group) {
    if (group == "tissue_segmentation") {
        return [
            level: args.level,
            mode: args.mode,
            kwargs: args.tissue_segmentation_kwargs,
        ]
    } else if (group == "image_patches") {
        return [
            patch_width_pixel: args.patch_width_pixel,
            patch_overlap_pixel: args.patch_overlap_pixel,
        ]
    } else {
        exit 1, "Unknown argument group: ${group}"
    }
}

// Targets to segment; cells unless segment_cells is false (null counts as on, as for a partial map), nuclei opt-in.
// Truthiness, not == true: a bare flag arrives as the String "true" (rejectStringBooleans refuses any other text).
def segmentationTargets(Map args) {
    def targets = []
    if (args.segment_cells == null || args.segment_cells) {
        targets << 'cells'
    }
    if (args.segment_nuclei) {
        targets << 'nuclei'
    }
    return targets
}

// One spec per enabled method x target. Unset values are dropped, not defaulted: sopa's
// defaults are applied per method downstream.
def segmentationSpecs(Map args) {
    def specs = []
    def targets = segmentationTargets(args)
    def image = args.use_projection ? 'projected' : 'full'
    def segmentation_kwargs = [
        min_area: toNumber('min_area_pixels2', args.min_area_pixels2),
        clip_limit: toNumber('clip_limit', args.clip_limit),
        clahe_kernel_size: toNumber('clahe_kernel_size', args.clahe_kernel_size),
        gaussian_sigma: toNumber('gaussian_sigma', args.gaussian_sigma),
    ].findAll { _k, v -> v != null }

    if (args.use_cellpose) {
        targets.each { target ->
            def channels
            if (args.use_projection) {
                channels = target == 'cells' ? ['cell', 'nuclear'] : ['nuclear']
            } else {
                def names = getChannels(args.cellpose_channels, false)
                channels = target == 'cells' ? names : [names.last()]
            }
            specs << [
                name: "cellpose_${target}".toString(),
                method: 'cellpose',
                target: target,
                image: image,
                channels: channels,
                // diameter: sopa requires it; cellpose 4 rescales by 30 / diameter, so 30 means no rescaling.
                method_kwargs: mergeMethodKwargs('cellpose', [
                    diameter: 30,
                    flow_threshold: toNumber('flow_threshold', args.flow_threshold),
                    cellprob_threshold: toNumber('cellprob_threshold', args.cellprob_threshold),
                    pretrained_model: args.pretrained_model,
                ], args.cellpose_kwargs),
                segmentation_kwargs: segmentation_kwargs,
                gpu: args.use_gpu ? true : false,
            ]
        }
    }
    if (args.use_instanseg) {
        targets.each { target ->
            specs << [
                name: "instanseg_${target}".toString(),
                method: 'instanseg',
                target: target,
                // The projection is Cellpose's input only; its channels do not exist for InstanSeg.
                image: 'full',
                channels: getChannels(args.instanseg_channels, true),
                method_kwargs: mergeMethodKwargs('instanseg', [
                    model_type: args.instanseg_model_type,
                    pixel_size: toNumber('instanseg_pixel_size', args.instanseg_pixel_size),
                    target: target,
                ], args.instanseg_kwargs),
                segmentation_kwargs: segmentation_kwargs,
                gpu: false,
            ]
        }
    }
    return specs
}

// Free-form kwargs sit at the same level as the explicit ones, as sopa's CLI does; a clash is an error.
def mergeMethodKwargs(String method, Map explicit, Map extra) {
    def merged = explicit.findAll { _k, v -> v != null }
    (extra ?: [:]).each { k, v ->
        if (explicit.containsKey(k)) {
            error("${method}_kwargs key '${k}' collides with a dedicated parameter. Remove it from ${method}_kwargs.")
        }
        if (v != null) {
            merged[k] = v
        }
    }
    return merged
}

// Channels may be a string or a number (schema type ["string", "integer"]); left untyped so
// Groovy does not coerce silently.
def getChannels(channels, Boolean allow_null = false) {
    if (channels == null) {
        if (allow_null) {
            return null
        }
        exit 1, "cellpose_channels is required but was not set."
    }

    if (!(channels instanceof CharSequence) && !(channels instanceof Number)) {
        exit 1, "The channels parameter must be channel names separated by space, comma or " +
            "pipe characters, or a single channel number. Got a ${channels.getClass().simpleName}: ${channels}"
    }

    return channels.toString().split(/[ ,|]+/).findAll { it }
}

// Command-line values arrive as Strings and params cannot be reassigned, so numbers are parsed
// where used: in arithmetic "3000" * 0.65 is string repetition, and in kwargs JSON a str for sopa.
def toNumber(String name, value) {
    if (value == null || value instanceof Number) {
        return value
    }
    if (value instanceof CharSequence) {
        def text = value.toString().trim()
        if (text.isInteger()) {
            return text.toInteger()
        }
        if (text.isBigDecimal()) {
            return text.toBigDecimal()
        }
    }
    error("${name} must be a number, got '${value}'")
}

// GB one InstanSeg patch task asks for. Per megapixel at the model's 0.5 µm/px, peak_rss is flat
// to ~4 channels, then ~0.25 GB per channel (test7, dropbox run 00009); ~1.2x headroom.
def instansegMemoryGB(int n_channels, patch_width, pixel_size) {
    patch_width = toNumber('patch_width_pixel', patch_width)
    pixel_size = toNumber('instanseg_pixel_size', pixel_size)
    def megapixels = Math.pow(patch_width * pixel_size / 0.5, 2) / 1e6
    return Math.ceil(2 + megapixels * instansegGBPerMegapixel(n_channels)) as int
}

def instansegGBPerMegapixel(int n_channels) {
    return Math.max(1.3, 0.3 * n_channels)
}

// Largest patch_width_pixel, in steps of 100, whose request stays within gigabytes.
def instansegMaxPatchWidth(int n_channels, gigabytes, pixel_size) {
    pixel_size = toNumber('instanseg_pixel_size', pixel_size)
    def megapixels = (gigabytes - 2) / instansegGBPerMegapixel(n_channels)
    return ((Math.sqrt(megapixels * 1e6) * 0.5 / pixel_size / 100) as int) * 100
}

// Marker names InstanSeg reads when instanseg_channels is unset: nuclear stains, plus markers
// when segmenting cells. Autofluorescence and blank channels are left out.
def defaultInstansegChannels(List rows, String target) {
    def roles = target == 'nuclei' ? ['dna'] : ['dna', 'marker']
    return rows.findAll { it.channel_role in roles }.collect { it.marker_name }
}

def argsCLI(String group = null, Map args = null) {
    args = args ?: params

    if (group != null) {
        args = extractSubArgs(args, group)
    }

    return args
        .findAll { _key, _value -> _value != null }
        .collect { key, value -> stringifyItem(key, value) }
        .join(" ")
}


def argsToSpatialData(Map meta, String fullres_image_file) {
    // Bio-Formats-readable OME-TIFF is the only input; sopa's other readers are out of scope.
    def args = [
        technology: "ome_tif",
        kwargs: [:],
    ]

    return argsCLI(null, args)
}
