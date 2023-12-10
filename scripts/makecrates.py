"""
makecrates.py
Copyright 2017-2019 Adam Greig
Licensed under the MIT and Apache 2.0 licenses.

Autogenerate the crate Cargo.toml, build.rs, README.md and src/lib.rs files
based on available YAML files for each GD32 family.

Usage: python3 scripts/makecrates.py devices/
"""

import os
import glob
import os.path
import argparse
import re
import yaml

VERSION = "0.8.0"
SVD2RUST_VERSION = "0.30.1"

CRATE_DOC_FEATURES = {
    "gd32e1": ["rt", "gd32e103"],
    "gd32c1": ["rt", "gd32c103", "gd32c113"],
    "gd32e2": ["rt", "gd32e230", "gd32e231"],
    "gd32e5": ["rt", "gd32e503", "gd32e508"],
    "gd32f1": ["rt", "gd32f130", "gd32f190"],
    "gd32f2": ["rt", "gd32f205", "gd32f207"],
    "gd32f3": ["rt", "gd32f303", "gd32f307"],
}

CRATE_DOC_TARGETS = {
    "gd32e1": "thumbv7m-none-eabi",
    "gd32c1": "thumbv7m-none-eabi",
    "gd32e2": "thumbv8m.base-none-eabi",
    "gd32e5": "thumbv8m.base-none-eabi",
    "gd32f1": "thumbv7m-none-eabi",
    "gd32f2": "thumbv7m-none-eabi",
    "gd32f3": "thumbv7em-none-eabihf",
}

CARGO_TOML_TPL = """\
[package]
edition = "2018"
name = "{crate}"
version = "{version}"
authors = ["Andrew Walbran <qwandor@gmail.com>", "gd32-rs Contributors"]
description = "Device support crate for {family} devices"
repository = "https://github.com/gd32-rust/gd32-rs"
readme = "README.md"
keywords = ["gd32", "svd2rust", "no_std", "embedded"]
categories = ["embedded", "no-std"]
license = "MIT OR Apache-2.0"

[dependencies]
vcell = "0.1.3"
cortex-m = "0.7.7"

[dependencies.cortex-m-rt]
optional = true
version = "0.7.3"

[dependencies.critical-section]
optional = true
version = "1.1.2"

[package.metadata.docs.rs]
features = {docs_features}
default-target = "{doc_target}"
targets = []

[features]
default = []
rt = ["cortex-m-rt/device"]
{features}
"""

SRC_LIB_RS_TPL = """\
//! Peripheral access API for {family} microcontrollers
//! (generated using [svd2rust](https://github.com/rust-embedded/svd2rust)
//! {svd2rust_version})
//!
//! You can find an overview of the API here:
//! [svd2rust/#peripheral-api](https://docs.rs/svd2rust/{svd2rust_version}/svd2rust/#peripheral-api)
//!
//! For more details see the README here:
//! [gd32-rs](https://github.com/gd32-rust/gd32-rs)
//!
//! This crate supports all {family} devices; for the complete list please
//! see:
//! [{crate}](https://github.com/gd32-rust/gd32-rs-nightlies/tree/main/{crate})
//!
//! Due to doc build limitations, not all devices may be shown on docs.rs;
//! a representative few have been selected instead. For a complete list of
//! available registers and fields see: [gd32-rs Device Coverage](https://gd32-rust.github.io/gd32-rs/)

#![allow(non_camel_case_types)]
#![no_std]

mod generic;
pub use self::generic::*;

{mods}
"""

README_TPL = """\
# {crate}
This crate provides an autogenerated API for access to {family} peripherals.
The API is generated using [svd2rust] with patched svd files containing
extensive type-safe support. For more information please see the [main repo].

Refer to the [documentation] for full details.

[svd2rust]: https://github.com/japaric/svd2rust
[main repo]: https://github.com/gd32-rust/gd32-rs
[documentation]: https://docs.rs/{crate}/latest/{crate}/

## Usage
Each device supported by this crate is behind a feature gate so that you only
compile the device(s) you want. To use, in your Cargo.toml:

```toml
[dependencies.{crate}]
version = "{version}"
features = ["{device}", "rt", "critical-section"]
```

The `rt` feature is optional and brings in support for `cortex-m-rt`.

In your code:

```rust
use {crate}::{device};

let mut peripherals = {device}::Peripherals::take().unwrap();
let gpioa = &peripherals.GPIOA;
gpioa.odr.modify(|_, w| w.odr0().set_bit());
```

For full details on the autogenerated API, please see:
https://docs.rs/svd2rust/{svd2rust_version}/svd2rust/#peripheral-api

## Supported Devices

| Module | Devices | Links |
|:------:|:-------:|:-----:|
{devices}
"""


BUILD_TPL = """\
use std::env;
use std::fs;
use std::path::PathBuf;
fn main() {{
    if env::var_os("CARGO_FEATURE_RT").is_some() {{
        let out = &PathBuf::from(env::var_os("OUT_DIR").unwrap());
        println!("cargo:rustc-link-search={{}}", out.display());
        let device_file = {device_clauses};
        fs::copy(device_file, out.join("device.x")).unwrap();
        println!("cargo:rerun-if-changed={{}}", device_file);
    }}
    println!("cargo:rerun-if-changed=build.rs");
}}
"""


def read_device_table():
    path = os.path.join(
        os.path.abspath(os.path.split(__file__)[0]), os.pardir,
        "gd32_part_table.yaml")
    with open(path, encoding='utf-8') as f:
        table = yaml.safe_load(f)
    return table


def make_device_rows(table, family):
    rows = []
    for device, dt in table[family].items():
        links = "[{}]({}), [gigadevice.com]({})".format(
            dt['rm'], dt['rm_url'], dt['url'])
        members = ", ".join(m for m in dt['members'])
        rows.append("| {} | {} | {} |".format(device, members, links))
    return "\n".join(sorted(rows))


def make_features(devices):
    return "\n".join("{} = []".format(d) for d in sorted(devices))


def make_mods(devices):
    return "\n".join('#[cfg(feature = "{0}")]\npub mod {0};\n'.format(d)
                     for d in sorted(devices))


def make_device_clauses(devices):
    return " else ".join("""\
        if env::var_os("CARGO_FEATURE_{}").is_some() {{
            "src/{}/device.x"
        }}""".strip().format(d.upper(), d) for d in sorted(devices)) + \
            " else { panic!(\"No device features selected\"); }"


def main(devices_path, yes, families):
    devices = {}

    for path in glob.glob(os.path.join(devices_path, "*.yaml")):
        yamlfile = os.path.basename(path)
        family = re.match(r'gd32[a-z]+[0-9]', yamlfile)[0]
        device = os.path.splitext(yamlfile)[0].lower()
        if len(families) == 0 or family in families:
            if family not in devices:
                devices[family] = []
            devices[family].append(device)

    table = read_device_table()

    dirs = ", ".join(x.lower()+"/" for x in devices)
    print("Going to create/update the following directories:")
    print(dirs)
    if not yes:
        input("Enter to continue, ctrl-C to cancel")

    for family in devices:
        devices[family] = sorted(devices[family])
        crate = family.lower()
        features = make_features(devices[family])
        clauses = make_device_clauses(devices[family])
        mods = make_mods(devices[family])
        ufamily = family.upper()
        cargo_toml = CARGO_TOML_TPL.format(
            family=ufamily, crate=crate, version=VERSION, features=features,
            docs_features=str(CRATE_DOC_FEATURES[crate]),
            doc_target=CRATE_DOC_TARGETS[crate])
        readme = README_TPL.format(
            family=ufamily, crate=crate, device=devices[family][0],
            version=VERSION, svd2rust_version=SVD2RUST_VERSION,
            devices=make_device_rows(table, family))
        lib_rs = SRC_LIB_RS_TPL.format(family=ufamily, mods=mods, crate=crate,
                                       svd2rust_version=SVD2RUST_VERSION)
        build_rs = BUILD_TPL.format(device_clauses=clauses)

        os.makedirs(os.path.join(crate, "src"), exist_ok=True)
        with open(os.path.join(crate, "Cargo.toml"), "w") as f:
            f.write(cargo_toml)
        with open(os.path.join(crate, "README.md"), "w") as f:
            f.write(readme)
        with open(os.path.join(crate, "src", "lib.rs"), "w") as f:
            f.write(lib_rs)
        with open(os.path.join(crate, "build.rs"), "w") as f:
            f.write(build_rs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-y",
                        help="Assume 'yes' to prompt",
                        action="store_true")
    parser.add_argument("devices",
                        help="Path to device YAML files")
    parser.add_argument('--families',
                        help="Families of components to generate crates for",
                        nargs='+',
                        required=False,
                        metavar='FAMILY',
                        default=[],
                        type=str)
    args = parser.parse_args()
    main(args.devices, args.y, args.families)
