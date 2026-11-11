// Learned per-cell features for every spec (model) and segmentation method, then one write into the store per sample.

include { NIMBUS         } from '../../../modules/local/nimbus'
include { WRITE_FEATURES } from '../../../modules/local/write_features'
include { defaultNimbusChannels } from '../../../modules/local/utils'

workflow LEARNED_FEATURES {
    take:
    ch_sdata   // channel: [ val(meta), path(sdata) ] the store with segmentations written
    ch_markers // channel: [ val(meta), path(csv) ] the channels each image has; empty without a marker sheet
    specs      // list: spec maps from featureSpecs(params), shared by every sample
    methods    // list: segmentation methods, each scored separately

    main:
    def ch_versions = channel.empty()

    // Samples are keyed by meta.sdata_dir as a String, as in SEGMENTATION (a GString never equals a String).

    // remainder: true keeps a sample with no sheet (sheet is null), so given channels can still be checked when one exists.
    def ch_sample_rows = ch_sdata
        .join(ch_markers, remainder: true)
        .map { meta, sdata, sheet -> [meta, sdata, sheet ? sheet.splitCsv(header: true) : null] }

    // One row per sample, method and spec. Specs are shared objects: build new maps, never mutate one.
    def ch_sample_specs = ch_sample_rows.flatMap { meta, sdata, rows ->
        [methods, specs].combinations().collect { method, spec ->
            // A model with no branch below would be dropped and the store never written: fail instead.
            if (spec.model != 'nimbus') {
                error("Unknown learned-features model '${spec.model}'; add its branch to LEARNED_FEATURES.")
            }
            // Unknown names would fail inside the task; fail here and say which.
            if (rows != null && spec.channels) {
                def missing = spec.channels - rows*.marker_name
                if (missing) {
                    // error(), not assert: an assert inside an operator dies without its message.
                    error("Sample '${meta.sample}': nimbus_channels not in the marker sheet: ${missing.join(', ')}.")
                }
            }
            def channels = spec.channels ?: defaultNimbusChannels(rows ?: [])
            if (!channels) {
                error("Sample '${meta.sample}': no marker channels for nimbus. Set nimbus_channels, or mark channels 'marker' in the marker sheet.")
            }
            [meta, sdata, method, spec + [channels: channels]]
        }
    }

    // One branch per model; KRONOS and others add theirs here.
    def ch_by_model = ch_sample_specs.branch { _meta, _sdata, _method, spec ->
        nimbus: spec.model == 'nimbus'
    }

    (ch_nimbus, versions) = NIMBUS(ch_by_model.nimbus)
    ch_versions = ch_versions.mix(versions)

    // Every model's score table, as [meta, table]; the writer needs no more.
    def ch_scores = ch_nimbus.map { meta, _method, _spec, table, _provenance -> [meta, table] }

    // groupKey carries the table count, so a sample is written once all its tables are in.
    def n_tables = methods.size() * specs.size()
    def ch_sample_tables = ch_scores
        .map { meta, table -> [groupKey(meta.sdata_dir.toString(), n_tables), table] }
        .groupTuple()
        // Sorted by file name, so the write order and -resume do not depend on arrival order.
        .map { key, tables -> [key.toString(), tables.sort(false) { table -> table.name }] }

    // Tables carry no store; take it back by sample. join: one row per sample on both sides.
    def ch_to_write = ch_sdata
        .map { meta, sdata -> [meta.sdata_dir.toString(), meta, sdata] }
        .join(ch_sample_tables)
        .map { _sdata_dir, meta, sdata, tables -> [meta, sdata, tables] }

    (ch_written, versions) = WRITE_FEATURES(ch_to_write)
    ch_versions = ch_versions.mix(versions)

    emit:
    sdata    = ch_written  // channel: [ val(meta), path(sdata) ] with tables {method}_nimbus written
    versions = ch_versions // channel: [ path(versions.yml) ]
}
