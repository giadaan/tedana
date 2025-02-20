"""
Integration tests for "real" data
"""

import glob
import os
import re
import shutil
import tarfile
from gzip import GzipFile
from io import BytesIO

import pandas as pd
import pytest
import requests
from pkg_resources import resource_filename

from tedana.workflows import t2smap as t2smap_cli
from tedana.workflows import tedana as tedana_cli


def check_integration_outputs(fname, outpath):
    """
    Checks outputs of integration tests

    Parameters
    ----------
    fname : str
        Path to file with expected outputs
    outpath : str
        Path to output directory generated from integration tests
    """

    # Gets filepaths generated by integration test
    existing = [
        os.path.relpath(f, outpath)
        for f in glob.glob(os.path.join(outpath, "**"), recursive=True)[1:]
    ]

    # Checks for log file
    log_regex = "^tedana_[12][0-9]{3}-[0-9]{2}-[0-9]{2}T[0-9]{2}[0-9]{2}[0-9]{2}.tsv$"
    logfiles = [out for out in existing if re.match(log_regex, out)]
    assert len(logfiles) == 1

    # Removes logfile from list of existing files
    existing.remove(logfiles[0])

    # Compares remaining files with those expected
    with open(fname, "r") as f:
        tocheck = f.read().splitlines()
    tocheck = [os.path.normpath(path) for path in tocheck]
    assert sorted(tocheck) == sorted(existing)


def download_test_data(osf, outpath):
    """
    Downloads tar.gz data stored at `osf` and unpacks into `outpath`

    Parameters
    ----------
    osf : str
        URL to OSF file that contains data to be downloaded
    outpath : str
        Path to directory where OSF data should be extracted
    """

    req = requests.get(osf)
    req.raise_for_status()
    t = tarfile.open(fileobj=GzipFile(fileobj=BytesIO(req.content)))
    os.makedirs(outpath, exist_ok=True)
    t.extractall(outpath)


def test_integration_five_echo(skip_integration):
    """Integration test of the full tedana workflow using five-echo test data."""

    if skip_integration:
        pytest.skip("Skipping five-echo integration test")

    out_dir = "/tmp/data/five-echo/TED.five-echo"
    out_dir_manual = "/tmp/data/five-echo/TED.five-echo-manual"

    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)

    if os.path.exists(out_dir_manual):
        shutil.rmtree(out_dir_manual)

    # download data and run the test
    download_test_data("https://osf.io/9c42e/download", os.path.dirname(out_dir))
    prepend = "/tmp/data/five-echo/p06.SBJ01_S09_Task11_e"
    suffix = ".sm.nii.gz"
    datalist = [prepend + str(i + 1) + suffix for i in range(5)]
    echo_times = [15.4, 29.7, 44.0, 58.3, 72.6]
    tedana_cli.tedana_workflow(
        data=datalist,
        tes=echo_times,
        out_dir=out_dir,
        tedpca=0.95,
        fittype="curvefit",
        fixed_seed=49,
        tedort=True,
        verbose=True,
    )

    # Just a check on the component table pending a unit test of load_comptable
    comptable = os.path.join(out_dir, "desc-tedana_metrics.tsv")
    df = pd.read_table(comptable)
    assert isinstance(df, pd.DataFrame)

    # Test re-running, but use the CLI
    acc_comps = df.loc[df["classification"] == "ignored"].index.values
    acc_comps = [str(c) for c in acc_comps]
    mixing = os.path.join(out_dir, "desc-ICA_mixing.tsv")
    t2smap = os.path.join(out_dir, "T2starmap.nii.gz")
    args = (
        ["-d"]
        + datalist
        + ["-e"]
        + [str(te) for te in echo_times]
        + [
            "--out-dir",
            out_dir_manual,
            "--debug",
            "--verbose",
            "--manacc",
            *acc_comps,
            "--ctab",
            comptable,
            "--mix",
            mixing,
            "--t2smap",
            t2smap,
        ]
    )
    tedana_cli._main(args)

    # compare the generated output files
    fn = resource_filename("tedana", "tests/data/nih_five_echo_outputs_verbose.txt")
    check_integration_outputs(fn, out_dir)


def test_integration_four_echo(skip_integration):
    """Integration test of the full tedana workflow using four-echo test data"""

    if skip_integration:
        pytest.skip("Skipping four-echo integration test")

    out_dir = "/tmp/data/four-echo/TED.four-echo"
    out_dir_manual = "/tmp/data/four-echo/TED.four-echo-manual"

    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)

    if os.path.exists(out_dir_manual):
        shutil.rmtree(out_dir_manual)

    # download data and run the test
    download_test_data("https://osf.io/gnj73/download", os.path.dirname(out_dir))
    prepend = "/tmp/data/four-echo/"
    prepend += "sub-PILOT_ses-01_task-localizerDetection_run-01_echo-"
    suffix = "_space-sbref_desc-preproc_bold+orig.HEAD"
    datalist = [prepend + str(i + 1) + suffix for i in range(4)]
    tedana_cli.tedana_workflow(
        data=datalist,
        tes=[11.8, 28.04, 44.28, 60.52],
        out_dir=out_dir,
        tedpca="kundu-stabilize",
        gscontrol=["gsr", "mir"],
        png_cmap="bone",
        debug=True,
        verbose=True,
    )

    # Test re-running with the component table
    mixing_matrix = os.path.join(out_dir, "desc-ICA_mixing.tsv")
    comptable = os.path.join(out_dir, "desc-tedana_metrics.tsv")
    temporary_comptable = os.path.join(out_dir, "temporary_metrics.tsv")
    comptable_df = pd.read_table(comptable)
    comptable_df.loc[comptable_df["classification"] == "ignored", "classification"] = "accepted"
    comptable_df.to_csv(temporary_comptable, sep="\t", index=False)
    tedana_cli.tedana_workflow(
        data=datalist,
        tes=[11.8, 28.04, 44.28, 60.52],
        out_dir=out_dir_manual,
        tedpca="kundu-stabilize",
        gscontrol=["gsr", "mir"],
        png_cmap="bone",
        mixm=mixing_matrix,
        ctab=temporary_comptable,
        debug=True,
        verbose=False,
    )
    os.remove(temporary_comptable)

    # compare the generated output files
    fn = resource_filename("tedana", "tests/data/fiu_four_echo_outputs.txt")

    check_integration_outputs(fn, out_dir)


def test_integration_three_echo(skip_integration):
    """Integration test of the full tedana workflow using three-echo test data"""

    if skip_integration:
        pytest.skip("Skipping three-echo integration test")

    out_dir = "/tmp/data/three-echo/TED.three-echo"
    out_dir_manual = "/tmp/data/three-echo/TED.three-echo-rerun"

    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)

    if os.path.exists(out_dir_manual):
        shutil.rmtree(out_dir_manual)

    # download data and run the test
    download_test_data("https://osf.io/rqhfc/download", os.path.dirname(out_dir))
    tedana_cli.tedana_workflow(
        data="/tmp/data/three-echo/three_echo_Cornell_zcat.nii.gz",
        tes=[14.5, 38.5, 62.5],
        out_dir=out_dir,
        low_mem=True,
        tedpca="aic",
    )

    # Test re-running, but use the CLI
    args = [
        "-d",
        "/tmp/data/three-echo/three_echo_Cornell_zcat.nii.gz",
        "-e",
        "14.5",
        "38.5",
        "62.5",
        "--out-dir",
        out_dir_manual,
        "--debug",
        "--verbose",
        "--ctab",
        os.path.join(out_dir, "desc-tedana_metrics.tsv"),
        "--mix",
        os.path.join(out_dir, "desc-ICA_mixing.tsv"),
    ]
    tedana_cli._main(args)

    # compare the generated output files
    fn = resource_filename("tedana", "tests/data/cornell_three_echo_outputs.txt")
    check_integration_outputs(fn, out_dir)


def test_integration_t2smap(skip_integration):
    """Integration test of the full t2smap workflow using five-echo test data"""
    if skip_integration:
        pytest.skip("Skipping t2smap integration test")
    out_dir = "/tmp/data/five-echo/t2smap_five-echo"
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)

    # download data and run the test
    download_test_data("https://osf.io/9c42e/download", os.path.dirname(out_dir))
    prepend = "/tmp/data/five-echo/p06.SBJ01_S09_Task11_e"
    suffix = ".sm.nii.gz"
    datalist = [prepend + str(i + 1) + suffix for i in range(5)]
    echo_times = [15.4, 29.7, 44.0, 58.3, 72.6]
    args = (
        ["-d"]
        + datalist
        + ["-e"]
        + [str(te) for te in echo_times]
        + ["--out-dir", out_dir, "--fittype", "curvefit"]
    )
    t2smap_cli._main(args)

    # compare the generated output files
    fname = resource_filename("tedana", "tests/data/nih_five_echo_outputs_t2smap.txt")
    # Gets filepaths generated by integration test
    existing = [
        os.path.relpath(f, out_dir)
        for f in glob.glob(os.path.join(out_dir, "**"), recursive=True)[1:]
    ]

    # Compares remaining files with those expected
    with open(fname, "r") as f:
        tocheck = f.read().splitlines()
    assert sorted(tocheck) == sorted(existing)
