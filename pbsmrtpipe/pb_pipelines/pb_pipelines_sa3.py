import logging
import functools

from pbsmrtpipe.core import register_pipeline
from pbsmrtpipe.constants import to_pipeline_ns, ENTRY_PREFIX

log = logging.getLogger(__name__)


def _to_entry(entry_prefix, value):
    return "".join([entry_prefix, value])

to_entry = functools.partial(_to_entry, ENTRY_PREFIX)


class Constants(object):

    ENTRY_RS_MOVIE_XML = to_entry("rs_movie_xml")
    ENTRY_INPUT_XML = to_entry("eid_input_xml")
    ENTRY_REF_FASTA = to_entry("eid_ref_fasta")

    ENTRY_DS_REF = to_entry("eid_ref_dataset")
    ENTRY_BARCODE_FASTA = to_entry("eid_barcode_fasta")
    ENTRY_BAM_ALIGNMENT = to_entry("eid_bam_alignment")
    ENTRY_DS_HDF = to_entry("eid_hdfsubread")
    ENTRY_DS_SUBREAD = to_entry("eid_subread")
    ENTRY_DS_ALIGN = to_entry("eid_alignment")
    ENTRY_DS_CCS = to_entry("eid_ccs")


class Tags(object):
    # General Analysis Categories
    MAP = "mapping"
    CONSENSUS = "consensus"
    RPT = "reports"
    CCS = "ccs"
    LAA = "laa"
    MOD_DET = "modification-detection"
    MOTIF = "motif-analysis"
    ISOSEQ = "isoseq"
    DENOVO = "denovo"
    SAT = "sat"

    # File format converters
    CONVERTER = "converters"

    # These pipelines will NOT show up in the UI
    # Development/Diagnostic
    DEV = "dev"
    # Internal Analysis
    INTERNAL = "internal"

    RESEQ = (MAP, CONSENSUS)
    RESEQ_RPT = (MAP, CONSENSUS, RPT)
    RESEQ_IRPT = (MAP, CONSENSUS, RPT, INTERNAL)
    RESEQ_MOD_DET = (MAP, CONSENSUS, MOD_DET)
    RESEQ_MOTIF = (MAP, CONSENSUS, MOD_DET, MOTIF)


def sa3_register(relative_id, display_name, version, tags=(), task_options=None):
    pipeline_id = to_pipeline_ns(relative_id)
    return register_pipeline(pipeline_id, display_name, version, tags=tags, task_options=task_options)


def _core_align(subread_ds, reference_ds):
    # Call blasr/pbalign
    b3 = [(subread_ds, "pbalign.tasks.pbalign:0"),
          (reference_ds, "pbalign.tasks.pbalign:1")]
    return b3


def _core_align_plus(subread_ds, reference_ds):
    bs = _core_align(subread_ds, reference_ds)

    b4 = [("pbalign.tasks.pbalign:0", "pbreports.tasks.mapping_stats:0")]

    b5 = [("pbalign.tasks.pbalign:0", "pbalign.tasks.consolidate_bam:0")]

    return bs + b4 + b5


def _core_gc(alignment_ds, reference_ds):
    b1 = [(reference_ds, "genomic_consensus.tasks.variantcaller:1"),
          (alignment_ds, "genomic_consensus.tasks.variantcaller:0")]

    return b1


def _core_gc_plus(alignment_ds, reference_ds):
    """
    Returns a list of core bindings
    """

    # Need to have a better model to avoid copy any paste. This is defined in the
    # fat resquencing pipeline.
    # Summarize Coverage
    b1 = _core_gc(alignment_ds, reference_ds)

    b2 = [(alignment_ds, "pbreports.tasks.summarize_coverage:0"),
          (reference_ds, "pbreports.tasks.summarize_coverage:1")]

    b3 = [("pbreports.tasks.summarize_coverage:0", "genomic_consensus.tasks.summarize_consensus:0"),
          ("genomic_consensus.tasks.variantcaller:0", "genomic_consensus.tasks.summarize_consensus:1")]

    # Consensus Reports - variants
    b4 = [(reference_ds, "pbreports.tasks.variants_report:0"),
          ("genomic_consensus.tasks.summarize_consensus:0", "pbreports.tasks.variants_report:1"),
          ("genomic_consensus.tasks.variantcaller:0", "pbreports.tasks.variants_report:2")]

    # Consensus Reports - top variants
    b5 = [("genomic_consensus.tasks.variantcaller:0", "pbreports.tasks.top_variants:0"),
          (reference_ds, "pbreports.tasks.top_variants:1")]

    return b1 + b2 + b3 + b4 + b5


@sa3_register("sa3_fetch", "RS Movie to Subread DataSet", "0.1.0", tags=(Tags.CONVERTER, ))
def sa3_fetch():
    """
    Convert RS movie metadata XML to Subread DataSet XML
    """

    # convert to RS dataset
    b1 = [(Constants.ENTRY_RS_MOVIE_XML, "pbscala.tasks.rs_movie_to_ds_rtc:0")]

    b2 = [("pbscala.tasks.rs_movie_to_ds_rtc:0", "pbsmrtpipe.tasks.h5_subreads_to_subread:0")]

    return b1 + b2


@sa3_register("sa3_align", "RS movie Align", "0.1.0", tags=(Tags.MAP, ))
def sa3_align():
    """
    Perform mapping to reference sequence, starting from RS movie XML
    """
    # convert to RS dataset
    b1 = [(Constants.ENTRY_RS_MOVIE_XML, "pbscala.tasks.rs_movie_to_ds_rtc:0")]

    # h5 dataset to subread dataset via bax2bam
    b2 = [("pbscala.tasks.rs_movie_to_ds_rtc:0", "pbsmrtpipe.tasks.h5_subreads_to_subread:0")]

    bxs = _core_align_plus("pbsmrtpipe.tasks.h5_subreads_to_subread:0", Constants.ENTRY_DS_REF)

    return b1 + b2 + bxs


@sa3_register("sa3_resequencing", "RS movie Resequencing", "0.1.0", tags=Tags.RESEQ)
def sa3_resequencing():
    """
    Resequencing Pipeline - Blasr mapping and Genomic Consensus, starting from
    RS movie XML
    """
    return _core_gc("pbsmrtpipe.pipelines.sa3_align:pbalign.tasks.pbalign:0", Constants.ENTRY_DS_REF)


@sa3_register("sa3_hdfsubread_to_subread", "Convert RS to BAM", "0.1.0", tags=(Tags.CONVERTER, ))
def hdf_subread_converter():
    """
    Import HdfSubreadSet (bax.h5 basecalling files) to SubreadSet (.bam files)
    """
    b2 = [(Constants.ENTRY_DS_HDF, "pbsmrtpipe.tasks.h5_subreads_to_subread:0")]

    return b2


@sa3_register("sa3_ds_align", "SubreadSet Mapping", "0.1.0", tags=(Tags.MAP, Tags.INTERNAL))
def ds_align():
    """
    Perform Blasr mapping to reference sequence
    """
    return _core_align_plus(Constants.ENTRY_DS_SUBREAD, Constants.ENTRY_DS_REF)

RESEQUENCING_TASK_OPTIONS = {
    "genomic_consensus.task_options.diploid": False,
    "pbalign.task_options.algorithm_options": "-minMatch 12 -bestn 10 -minPctIdentity 70.0",
    "pbalign.task_options.concordant": True,
}


@sa3_register("sa3_ds_genomic_consensus", "Genomic Consensus", "0.1.0",
              tags=(Tags.CONSENSUS, Tags.INTERNAL),
            task_options=RESEQUENCING_TASK_OPTIONS)
def ds_genomic_consenus():
    """
    Run Genomic Consensus, starting from an existing AlignmentSet
    """
    return _core_gc_plus(Constants.ENTRY_DS_ALIGN, Constants.ENTRY_DS_REF)


@sa3_register("sa3_ds_resequencing", "Resequencing", "0.1.0",
              tags=Tags.RESEQ, task_options=RESEQUENCING_TASK_OPTIONS)
def ds_resequencing():
    """
    Core Resequencing Pipeline - Blasr mapping and Genomic Consensus
    """
    return _core_gc("pbsmrtpipe.pipelines.sa3_ds_align:pbalign.tasks.pbalign:0", Constants.ENTRY_DS_REF)


_OPTIONS = RESEQUENCING_TASK_OPTIONS.copy()
_OPTIONS["pbalign.task_options.consolidate_aligned_bam"] = True


@sa3_register("sa3_ds_resequencing_fat",
              "SubreadSet Resequencing With GC Extras and Reports", "0.1.0",
              task_options=_OPTIONS, tags=Tags.RESEQ_IRPT)
def ds_fat_resequencing():
    """
    Full Resequencing Pipeline - Blasr mapping and Genomic Consensus, plus
    additional reports
    """

    return _core_gc_plus("pbsmrtpipe.pipelines.sa3_ds_resequencing:pbalign.tasks.pbalign:0", Constants.ENTRY_DS_REF)


def _core_mod_detection(alignment_ds, reference_ds):
    bs = []
    _add = bs.append

    # AlignmentSet, ReferenceSet
    _add((alignment_ds, "kinetics_tools.tasks.ipd_summary:0"))
    _add((reference_ds, 'kinetics_tools.tasks.ipd_summary:1'))

    _add(('kinetics_tools.tasks.ipd_summary:1', 'pbreports.tasks.modifications_report:0'))
    return bs


BASEMODS_TASK_OPTIONS = dict(RESEQUENCING_TASK_OPTIONS)
BASEMODS_TASK_OPTIONS["kinetics_tools.task_options.pvalue"] = 0.001

@sa3_register("ds_modification_detection",
                   'Base Modification Detection', "0.1.0",
                   tags=(Tags.MOD_DET, ), task_options=BASEMODS_TASK_OPTIONS)
def rs_modification_detection_1():
    """
    Base Modification Analysis Pipeline - performs resequencing workflow
    and detects methylated bases from kinetic data
    """
    b1 = _core_mod_detection("pbsmrtpipe.pipelines.sa3_ds_resequencing_fat:pbalign.tasks.pbalign:0", Constants.ENTRY_DS_REF)
    b2 = [
        # basemods.gff
        ("kinetics_tools.tasks.ipd_summary:0", "kinetics_tools.tasks.summarize_modifications:0"),
        # alignment_summary_final.gff
        ("pbsmrtpipe.pipelines.sa3_ds_resequencing_fat:genomic_consensus.tasks.summarize_consensus:0", "kinetics_tools.tasks.summarize_modifications:1")
    ]
    return b1 + b2


def _core_motif_analysis(ipd_gff, reference_ds):
    bs = []
    x = bs.append
    # Find Motifs. AlignmentSet, ReferenceSet
    x((ipd_gff, 'motif_maker.tasks.find_motifs:0'))  # basemods GFF
    x((reference_ds, 'motif_maker.tasks.find_motifs:1'))

    # Make Motifs GFF: ipdSummary GFF, ipdSummary CSV, MotifMaker CSV, REF
    x((ipd_gff, 'motif_maker.tasks.reprocess:0'))  # GFF
    # XXX this is not currently used
    #_add(('pbsmrtpipe.pipelines.ds_modification_detection:kinetics_tools.tasks.ipd_summary:1', 'motif_maker.tasks.reprocess:1')) # CSV
    x(('motif_maker.tasks.find_motifs:0', 'motif_maker.tasks.reprocess:1'))  # motifs GFF
    x((reference_ds, 'motif_maker.tasks.reprocess:2'))

    # MK Note. Pat did something odd here that I can't remember the specifics
    x(('motif_maker.tasks.reprocess:0', 'pbreports.tasks.motifs_report:0'))
    x(('motif_maker.tasks.find_motifs:0', 'pbreports.tasks.motifs_report:1'))

    return bs


@sa3_register("ds_modification_motif_analysis", 'Base Modification and Motif Analysis', "0.1.0",
              tags=(Tags.MOTIF, ), task_options=BASEMODS_TASK_OPTIONS)
def rs_modification_and_motif_analysis_1():
    """
    Modification and Motif Analysis Pipeline - performs resequencing workflow,
    detects methylated bases from kinetic data, and identifies consensus
    nucleotide motifs
    """
    return _core_motif_analysis(
        'pbsmrtpipe.pipelines.ds_modification_detection:kinetics_tools.tasks.ipd_summary:0', Constants.ENTRY_DS_REF)


@sa3_register("pb_modification_detection", 'PacBio Internal Modification Analysis', "0.1.0",
              tags=(Tags.RPT, Tags.MOD_DET, Tags.INTERNAL ),
              task_options={"kinetics_tools.task_options.pvalue":0.001})
def pb_modification_analysis_1():
    """
    Internal base modification analysis pipeline, starting from an existing
    AlignmentSet
    """
    return _core_mod_detection(Constants.ENTRY_DS_ALIGN, Constants.ENTRY_DS_REF)


@sa3_register("pb_modification_motif_analysis", 'PacBio Internal Modification and Motif Analysis', "0.1.0",
              tags=Tags.RESEQ_MOTIF, task_options={"kinetics_tools.task_options.pvalue": 0.001})
def pb_modification_and_motif_analysis_1():
    """
    Internal base modification and motif analysis pipeline, starting from an
    existing AlignmentSet
    """
    return _core_motif_analysis('pbsmrtpipe.pipelines.pb_modification_detection:kinetics_tools.tasks.ipd_summary:0',
                                Constants.ENTRY_DS_REF)

SAT_TASK_OPTIONS = RESEQUENCING_TASK_OPTIONS.copy()
SAT_TASK_OPTIONS["genomic_consensus.task_options.algorithm"] = "plurality"

@sa3_register("sa3_sat", 'Site Acceptance Test (SAT)', "0.1.0",
              tags=(Tags.MAP, Tags.CONSENSUS, Tags.RPT, Tags.SAT),
              task_options=SAT_TASK_OPTIONS)
def rs_site_acceptance_test_1():
    """
    Site Acceptance Test - lambda genome resequencing used to validate new
    PacBio installations
    """

    # AlignmentSet, GFF, mapping Report
    x = [("pbsmrtpipe.pipelines.sa3_ds_resequencing:pbalign.tasks.pbalign:0", "pbreports.tasks.sat_report:0"),
         ("pbsmrtpipe.pipelines.sa3_ds_resequencing_fat:pbreports.tasks.variants_report:0", "pbreports.tasks.sat_report:1"),
         ("pbsmrtpipe.pipelines.sa3_ds_resequencing_fat:pbreports.tasks.mapping_stats:0", "pbreports.tasks.sat_report:2")]

    return x


def _core_export_fastx(subread_ds):
    b1 = [(subread_ds, "pbsmrtpipe.tasks.bam2fasta:0")]
    b2 = [(subread_ds, "pbsmrtpipe.tasks.bam2fastq:0")]
    return b1 + b2


def _core_export_fastx_ccs(ccs_ds):
    b1 = [(ccs_ds, "pbsmrtpipe.tasks.bam2fasta_ccs:0")]
    b2 = [(ccs_ds, "pbsmrtpipe.tasks.bam2fastq_ccs:0")]
    return b1 + b2


def _core_laa(subread_ds):
    # Call ccs
    b3 = [(subread_ds, "pblaa.tasks.laa:0")]
    return b3


@sa3_register("sa3_ds_laa", "Long Amplicon Analysis (LAA 2)", "0.1.0", tags=(Tags.LAA, ))
def ds_laa():
    """
    Basic Long Amplicon Analysis (LAA) pipeline, starting from subreads.
    """
    subreadset = Constants.ENTRY_DS_SUBREAD

    laa = _core_laa(subreadset)

    consensus_report = [("pblaa.tasks.laa:1", "pbreports.tasks.amplicon_analysis_consensus:0")]

    return laa + consensus_report


def _core_ccs(subread_ds):
    # Call ccs
    b3 = [(subread_ds, "pbccs.tasks.ccs:0")]
    # CCS report
    b4 = [("pbccs.tasks.ccs:0", "pbreports.tasks.ccs_report:0")]
    b5 = _core_export_fastx_ccs("pbccs.tasks.ccs:0")
    return b3 + b4 + b5


@sa3_register("sa3_ds_ccs", "Circular Consensus Sequences (CCS 2)", "0.1.0", tags=(Tags.CCS, ))
def ds_ccs():
    """
    Basic ConsensusRead (CCS) pipeline, starting from subreads.
    """
    return _core_ccs(Constants.ENTRY_DS_SUBREAD)


def _core_ccs_align(ccs_ds):
    # pbalign w/CCS input
    b3 = [(ccs_ds, "pbalign.tasks.pbalign_ccs:0"),
          (Constants.ENTRY_DS_REF, "pbalign.tasks.pbalign_ccs:1")]
    # mapping_stats_report (CCS version)
    b4 = [("pbalign.tasks.pbalign_ccs:0",
           "pbreports.tasks.mapping_stats_ccs:0")]
    return b3+b4


@sa3_register("sa3_ds_ccs_align", "CCS Mapping", "0.1.0", tags=(Tags.CCS, Tags.MAP, ))
def ds_align_ccs():
    """
    ConsensusRead (CCS) + Mapping pipeline, starting from subreads.
    """
    return _core_ccs_align("pbsmrtpipe.pipelines.sa3_ds_ccs:pbccs.tasks.ccs:0")


@sa3_register("pb_ccs_align", "Internal Consensus Read Mapping", "0.1.0", tags=(Tags.MAP, Tags.CCS, Tags.INTERNAL))
def pb_align_ccs():
    """
    Internal ConsensusRead (CCS) alignment pipeline, starting from an existing
    ConsensusReadSet.
    """
    return _core_ccs_align(Constants.ENTRY_DS_CCS)


def _core_isoseq_classify(ccs_ds):
    b3 = [ # classify all CCS reads - CHUNKED (ContigSet scatter)
        (ccs_ds, "pbtranscript.tasks.classify:0")
    ]
    b4 = [ # pbreports isoseq_classify
        ("pbtranscript.tasks.classify:1", "pbreports.tasks.isoseq_classify:0"),
        ("pbtranscript.tasks.classify:3", "pbreports.tasks.isoseq_classify:1")
    ]
    return b3 + b4


def _core_isoseq_cluster(ccs_ds, flnc_ds, nfl_ds):
    b5 = [ # cluster reads and get consensus isoforms
        # full-length, non-chimeric transcripts
        (flnc_ds, "pbtranscript.tasks.cluster:0"),
        # non-full-length transcripts
        (nfl_ds, "pbtranscript.tasks.cluster:1"),
        (ccs_ds, "pbtranscript.tasks.cluster:2"),
        (Constants.ENTRY_DS_SUBREAD, "pbtranscript.tasks.cluster:3")
    ]
    b6 = [ # ice_partial to map non-full-lenth reads to consensus isoforms
        # non-full-length transcripts
        (nfl_ds, "pbtranscript.tasks.ice_partial:0"),
        # draft consensus isoforms
        ("pbtranscript.tasks.cluster:0", "pbtranscript.tasks.ice_partial:1"),
        (ccs_ds, "pbtranscript.tasks.ice_partial:2"),
    ]
    b7 = [
        (Constants.ENTRY_DS_SUBREAD, "pbtranscript.tasks.ice_quiver:0"),
        ("pbtranscript.tasks.cluster:0", "pbtranscript.tasks.ice_quiver:1"),
        ("pbtranscript.tasks.cluster:3", "pbtranscript.tasks.ice_quiver:2"),
        ("pbtranscript.tasks.ice_partial:0", "pbtranscript.tasks.ice_quiver:3")
    ]
    b8 = [
        (Constants.ENTRY_DS_SUBREAD, "pbtranscript.tasks.ice_quiver_postprocess:0"),
        ("pbtranscript.tasks.cluster:0", "pbtranscript.tasks.ice_quiver_postprocess:1"),
        ("pbtranscript.tasks.cluster:3", "pbtranscript.tasks.ice_quiver_postprocess:2"),
        ("pbtranscript.tasks.ice_partial:0", "pbtranscript.tasks.ice_quiver_postprocess:3"),
        ("pbtranscript.tasks.ice_quiver:0", "pbtranscript.tasks.ice_quiver_postprocess:4")
    ]
    b9 = [ # pbreports isoseq_cluster
        # draft consensus isoforms
        ("pbtranscript.tasks.cluster:0", "pbreports.tasks.isoseq_cluster:0"),
        # json report
        ("pbtranscript.tasks.cluster:1", "pbreports.tasks.isoseq_cluster:1"),
    ]

    return b5 + b6 + b7 + b8 + b9


ISOSEQ_TASK_OPTIONS = {
    "pbccs.task_options.min_passes":1,
    "pbccs.task_options.min_length":300,
    "pbccs.task_options.min_zscore":-9999,
    "pbccs.task_options.max_drop_fraction":0.80,
    "pbccs.task_options.min_predicted_accuracy":0.80
}


@sa3_register("sa3_ds_isoseq_classify", "IsoSeq Classify", "0.2.0",
              tags=(Tags.MAP, Tags.CCS, Tags.ISOSEQ),
              task_options=ISOSEQ_TASK_OPTIONS)
def ds_isoseq_classify():
    """
    Partial IsoSeq pipeline (classify step only), starting from subreads.
    """
    return _core_isoseq_classify("pbsmrtpipe.pipelines.sa3_ds_ccs:pbccs.tasks.ccs:0")


@sa3_register("sa3_ds_isoseq", "IsoSeq", "0.2.0",
              tags=(Tags.MAP, Tags.CCS, Tags.ISOSEQ),
              task_options=ISOSEQ_TASK_OPTIONS)
def ds_isoseq():
    """
    Main IsoSeq pipeline, starting from subreads.
    """
    b1 = _core_isoseq_classify("pbsmrtpipe.pipelines.sa3_ds_ccs:pbccs.tasks.ccs:0")
    b2 = _core_isoseq_cluster(
        "pbsmrtpipe.pipelines.sa3_ds_ccs:pbccs.tasks.ccs:0",
        "pbtranscript.tasks.classify:1",
        "pbtranscript.tasks.classify:2")
    return b1 + b2


@sa3_register("pb_isoseq", "Internal IsoSeq pipeline", "0.2.0", tags=(Tags.MAP, Tags.CCS, Tags.ISOSEQ, Tags.INTERNAL))
def pb_isoseq():
    """
    Internal IsoSeq pipeline starting from an existing CCS dataset.
    """
    b1 = _core_isoseq_classify(Constants.ENTRY_DS_CCS)
    b2 = _core_isoseq_cluster(
        Constants.ENTRY_DS_CCS,
        "pbtranscript.tasks.classify:1",
        "pbtranscript.tasks.classify:2")
    return b1 + b2


@sa3_register("pb_isoseq_cluster", "Internal IsoSeq clustering pipeline", "0.2.0", tags=(Tags.ISOSEQ, Tags.INTERNAL,))
def pb_isoseq_cluster():
    return _core_isoseq_cluster(Constants.ENTRY_DS_CCS,
        to_entry("e_flnc_fa"), to_entry("e_nfl_fa"))


# XXX will resurrect in the future
#@sa3_register("sa3_ds_isoseq_classify_align"),
#                   "IsoSeq Classification and GMAP Alignment", "0.1.0",
#                   tags=("isoseq", ),
#                   task_options=ISOSEQ_TASK_OPTIONS)
#def ds_isoseq_classify_align():
#    b1 = _core_isoseq_classify("pbsmrtpipe.pipelines.sa3_ds_ccs:pbccs.tasks.ccs:0")
#    b2 = [
#        # full-length, non-chimeric transcripts
#        ("pbtranscript.tasks.classify:1", "pbtranscript.tasks.gmap:0"),
#        (Constants.ENTRY_DS_REF, "pbtranscript.tasks.gmap:1")
#    ]
#    return b1 + b2
#
#
#@sa3_register("sa3_ds_isoseq_align"),
#                   "IsoSeq Pipeline plus GMAP alignment", "0.1.0",
#                   tags=("isoseq", ),
#                   task_options=ISOSEQ_TASK_OPTIONS)
#def ds_isoseq_align():
#    b1 = _core_isoseq_cluster("pbsmrtpipe.pipelines.sa3_ds_ccs:pbccs.tasks.ccs:0")
#    b2 = [
#        # use high-quality isoforms here? or something else?
#        ("pbtranscript.tasks.ice_quiver_postprocess:2",
#         "pbtranscript.tasks.gmap:0"),
#        (Constants.ENTRY_DS_REF, "pbtranscript.tasks.gmap:1")
#    ]
#    return b1 + b2

@sa3_register("sa3_ds_subreads_to_fastx", "SubreadSet to .fastx Conversion", "0.1.0", tags=(Tags.CONVERTER,))
def ds_subreads_to_fastx():
    """
    Export SubreadSet to FASTA and FASTQ formats
    """
    return _core_export_fastx(Constants.ENTRY_DS_SUBREAD)
