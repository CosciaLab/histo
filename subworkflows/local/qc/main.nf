// QC: fast metrics, slow images and an HTML report, split so a slow or failed image step
// does not cost the metrics. The metrics JSON is the machine-readable contract.

include { QC_METRICS } from '../../../modules/local/qc_metrics'
include { QC_IMAGES  } from '../../../modules/local/qc_images'
include { QC_REPORT  } from '../../../modules/local/qc_report'

workflow QC {
    take:
    ch_sdata         // channel: [ val(meta), path(sdata) ]
    ch_markers       // channel: [ val(meta), path(csv) ], or an empty channel
    ch_unsubtracted  // channel: [ val(meta), path(tif) ], or an empty channel
    ch_registration  // channel: [ val(meta), path(dir) ] Ashlar QC keyed by Ashlar's meta.id, or empty

    main:

    def ch_versions = channel.empty()

    // remainder: true keeps stores without a pre-subtraction image (no backsub) or marker
    // sheet (pre-stitched input); the missing side becomes [], meaning no flag in the module.
    def ch_qc_input = ch_sdata
        .join(ch_unsubtracted, remainder: true)
        .join(ch_markers, remainder: true)
        .map { meta, sdata, tif, markers -> [meta, sdata, tif ?: [], markers ?: []] }
        .filter { _meta, sdata, _tif, _markers -> sdata }

    QC_METRICS(ch_qc_input)
    ch_versions = ch_versions.mix(QC_METRICS.out.versions)

    if (params.use_qc_images) {
        QC_IMAGES(ch_qc_input.map { meta, sdata, _tif, markers -> [meta, sdata, markers] })
        ch_versions = ch_versions.mix(QC_IMAGES.out.versions)
        ch_report_input = QC_METRICS.out.metrics.join(QC_IMAGES.out.images)
    }
    else {
        ch_report_input = QC_METRICS.out.metrics.map { meta, metrics -> [meta, metrics, []] }
    }

    // Ashlar runs per sample, or per slide before dearraying, so match on id: a TMA core's
    // id is never its slide's, and the slide-level QC goes to MERGE_REPORT instead.
    ch_report_input = ch_report_input
        .map { meta, metrics, images -> [meta.id, meta, metrics, images] }
        .join(ch_registration.map { meta, dir -> [meta.id, dir] }, remainder: true)
        // Indexed, not destructured: remainder rows with no report side are only [id, null, dir].
        .filter { row -> row[1] != null }
        .map { row -> [row[1], row[2], row[3], row.size() > 4 && row[4] ? row[4] : []] }

    QC_REPORT(ch_report_input)
    ch_versions = ch_versions.mix(QC_REPORT.out.versions)

    emit:
    metrics  = QC_METRICS.out.metrics  // channel: [ val(meta), path(json) ] the machine-readable contract
    report   = QC_REPORT.out.report    // channel: [ val(meta), path(html) ]
    versions = ch_versions             // channel: [ path(versions.yml) ]
}
