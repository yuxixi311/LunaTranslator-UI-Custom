"""Offline, non-executing validator for the frozen Luna CPU wheel closure.

This module never fetches, installs, extracts or imports wheel contents. A future
caller supplies acquired archives plus a finalized 49-record manifest. Validation
is not acquisition authorization or legal clearance. All wheel members, including
notices, remain in the returned installation inventory.
"""
from __future__ import annotations

import base64
from collections import Counter
from dataclasses import dataclass, asdict, replace
from email import policy
from email.parser import BytesParser
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import struct
import unicodedata
from urllib.parse import urlparse, unquote
import zipfile

import packaging
from wheel_validation_codes import WHEEL_SUBCHECKS, METADATA_VERSION_OBSERVATIONS
from packaging.requirements import Requirement, InvalidRequirement
from packaging.specifiers import SpecifierSet, InvalidSpecifier
from packaging.tags import parse_tag
from packaging.utils import canonicalize_name, parse_wheel_filename, InvalidWheelFilename


# This frozen source snapshot deliberately excludes the obsolete plac proposal.
# No registry calls are made and no dependency resolver runs here.
_FIXED_RECORDS_JSON = r'''
[
  {
    "name": "annotated-doc",
    "version": "0.0.5",
    "wheel": {
      "bytes": 5302,
      "core_metadata_sha256": "8c24d70c5d9153d22123353a906042fd7603df2d15c2196290b0f8a962558c46",
      "filename": "annotated_doc-0.0.5-py3-none-any.whl",
      "requires_python": ">=3.9",
      "sha256": "117bac03a25ede5df5440e855b32d556049ca169ead221505badf432fed4b101",
      "url": "https://files.pythonhosted.org/packages/3e/30/e900b21425a860e195f32e37657aa1f7c7f2b1bfb26f03ca209b90933c06/annotated_doc-0.0.5-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.9",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "MIT",
      "legacy": null
    }
  },
  {
    "name": "annotated-types",
    "version": "0.8.0",
    "wheel": {
      "bytes": 13427,
      "core_metadata_sha256": "614985b278f601b8ef863f82783b991cc3ada4b89f592eb71c7c48c5f2ef2298",
      "filename": "annotated_types-0.8.0-py3-none-any.whl",
      "requires_python": ">=3.10",
      "sha256": "f072f4d804ea359e4eaf198b1af7a8b0943881a87f31bb764f8bf219bb9419e0",
      "url": "https://files.pythonhosted.org/packages/99/91/8acff4f5e50511b911bbccb72b8628a49c68ce14148cd9f6431094859a90/annotated_types-0.8.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.10",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": "MIT",
      "legacy": null
    }
  },
  {
    "name": "anyio",
    "version": "4.14.2",
    "wheel": {
      "bytes": 125813,
      "core_metadata_sha256": "c5e6fc4dfd833319913b287be7a30d9935e9208c7ef917630621855aaac4d419",
      "filename": "anyio-4.14.2-py3-none-any.whl",
      "requires_python": ">=3.10",
      "sha256": "9f505dda5ac9f0c8309b5e8bd445a8c2bf7246f3ce950121e45ea15bc41d1494",
      "url": "https://files.pythonhosted.org/packages/da/35/f2287558c17e29fafc8ef3daf819bb9834061cfa43bff8014f7df7f63bdc/anyio-4.14.2-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.10",
    "requires_dist_applicable": [
      "idna>=2.8",
      "typing_extensions>=4.5; python_version < \"3.13\""
    ],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "MIT",
      "legacy": null
    }
  },
  {
    "name": "blis",
    "version": "1.3.3",
    "wheel": {
      "bytes": 11366550,
      "core_metadata_sha256": "535aa94ba125115b4c5af94f067168f0bb38f227bfa7d1b5dccf56e66ff66cb4",
      "filename": "blis-1.3.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "requires_python": "<3.15,>=3.9",
      "sha256": "1ef6d6e2b599a3a2788eb6d9b443533961265aa4ec49d574ed4bb846e548dcdb",
      "url": "https://files.pythonhosted.org/packages/d5/ad/58deaa3ad856dd3cc96493e40ffd2ed043d18d4d304f85a65cde1ccbf644/blis-1.3.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "yanked": false
    },
    "requires_python": "<3.15,>=3.9",
    "requires_dist_applicable": [
      "numpy<3.0.0,>=1.19.0; python_version >= \"3.9\""
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: BSD License"
      ],
      "expression": null,
      "legacy": "BSD"
    }
  },
  {
    "name": "catalogue",
    "version": "2.0.10",
    "wheel": {
      "bytes": 17325,
      "core_metadata_sha256": "570324cbd96a88587fd07f0cc7c29e0bc3c92b6d097d32e09775f8fcdd6576d2",
      "filename": "catalogue-2.0.10-py3-none-any.whl",
      "requires_python": ">=3.6",
      "sha256": "58c2de0020aa90f4a2da7dfad161bf7b3b054c86a5f09fcedc0b2b740c109a9f",
      "url": "https://files.pythonhosted.org/packages/9e/96/d32b941a501ab566a16358d68b6eb4e4acc373fab3c3c4d7d9e649f7b4bb/catalogue-2.0.10-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.6",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "certifi",
    "version": "2026.7.22",
    "wheel": {
      "bytes": 136983,
      "core_metadata_sha256": "ef5af1638fbb23676ac3c5777dfcfc2cd9c348fe4172ed5ba3d277655b248090",
      "filename": "certifi-2026.7.22-py3-none-any.whl",
      "requires_python": ">=3.7",
      "sha256": "62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775",
      "url": "https://files.pythonhosted.org/packages/0b/a7/71ac2cff56fec219ed242bb11b8efb69fcc4bec75db06fb7bfe35de520e6/certifi-2026.7.22-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.7",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)"
      ],
      "expression": null,
      "legacy": "MPL-2.0"
    }
  },
  {
    "name": "charset-normalizer",
    "version": "3.5.1",
    "wheel": {
      "bytes": 248801,
      "core_metadata_sha256": "955c93827d59f1280f6d6a76b1e11bfb999cc65a55df83a6f9b28b7bc0e467f6",
      "filename": "charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
      "requires_python": ">=3.7",
      "sha256": "b9af956078716df40d985fb0dfeb2c2120c5ca92ba4ff4b388acfd01cdc14d08",
      "url": "https://files.pythonhosted.org/packages/6f/89/bb5108dc6c3651dca963f2b0a3ba19bbcb370c94e1b6d3e0e844a58e6dca/charset_normalizer-3.5.1-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
      "yanked": false
    },
    "requires_python": ">=3.7",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "click",
    "version": "8.4.2",
    "wheel": {
      "bytes": 119243,
      "core_metadata_sha256": "194c9dd81d567f9081f026c7e401060fbafa7bc147c8e0a58b3668b40a64c031",
      "filename": "click-8.4.2-py3-none-any.whl",
      "requires_python": ">=3.10",
      "sha256": "e6f9f66136c816745b9d65817da91d61d957fb16e02e4dcd0552553c5a197b76",
      "url": "https://files.pythonhosted.org/packages/fb/e2/79c688af8b210d232694e31e59da9f6ec747bae31c3f5946e4e9b98860d5/click-8.4.2-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.10",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "BSD-3-Clause",
      "legacy": null
    }
  },
  {
    "name": "cloudpathlib",
    "version": "0.24.0",
    "wheel": {
      "bytes": 63214,
      "core_metadata_sha256": "9d662ea44a30515c79ea6dbd8f0acff9635652113dc894a24324c9cc833a1f02",
      "filename": "cloudpathlib-0.24.0-py3-none-any.whl",
      "requires_python": ">=3.9",
      "sha256": "b1c51e2d2ec7dc4fed6538991f4aea849d6cf11a7e6b9069f86e461aa1f9b5b4",
      "url": "https://files.pythonhosted.org/packages/c2/5b/ba933f896d9b0b07608d575a8501e2b4e32166b60d84c430a4a7285ebe64/cloudpathlib-0.24.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.9",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": null
    }
  },
  {
    "name": "confection",
    "version": "1.3.3",
    "wheel": {
      "bytes": 35902,
      "core_metadata_sha256": "19791218537d8fe97ed57409c2784f7c7c7e7f443df2d08d7042187e32effad3",
      "filename": "confection-1.3.3-py3-none-any.whl",
      "requires_python": ">=3.10",
      "sha256": "b9fef9ee84b237ef4611ec3eb5797b70e13063e6310ad9f15536373f5e313c82",
      "url": "https://files.pythonhosted.org/packages/8d/e4/d66708bdf0d92fb4d49b22cdff4b10cec38aca5dcd7e81d909bb55c65cd7/confection-1.3.3-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.10",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "cymem",
    "version": "2.0.13",
    "wheel": {
      "bytes": 260843,
      "core_metadata_sha256": "615faac88aa1a2a800731e4add6f0be60967502a37a9c9b3bfd8feed5cc4f99a",
      "filename": "cymem-2.0.13-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "requires_python": "<3.15,>=3.9",
      "sha256": "f190a92fe46197ee64d32560eb121c2809bb843341733227f51538ce77b3410d",
      "url": "https://files.pythonhosted.org/packages/eb/12/678d16f7aa1996f947bf17b8cfb917ea9c9674ef5e2bd3690c04123d5680/cymem-2.0.13-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "yanked": false
    },
    "requires_python": "<3.15,>=3.9",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "ginza",
    "version": "5.2.0",
    "wheel": {
      "bytes": 21203,
      "core_metadata_sha256": "9da041501f7b3008f3a871721a8886b7e720fff9a1dbe775c2a32089b5168d76",
      "filename": "ginza-5.2.0-py3-none-any.whl",
      "requires_python": ">=3.8",
      "sha256": "0c81e69fc34070cdba583f6c35b701b0aa60ef486d73a052fe32917c47e55125",
      "url": "https://files.pythonhosted.org/packages/7e/6f/beaaeac69a027d88064a450466d2f88d329d360dfbc54c78d0af4796a62d/ginza-5.2.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.8",
    "requires_dist_applicable": [
      "spacy<4.0.0,>=3.4.4",
      "plac>=1.3.3",
      "SudachiPy<0.7.0,>=0.6.2",
      "SudachiDict-core>=20210802"
    ],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "h11",
    "version": "0.16.0",
    "wheel": {
      "bytes": 37515,
      "core_metadata_sha256": "28f326098ac09fcba79b8f180f96087c841fe2456215cb7b872a9c7d5cd19d64",
      "filename": "h11-0.16.0-py3-none-any.whl",
      "requires_python": ">=3.8",
      "sha256": "63cf8bbe7522de3bf65932fda1d9c2772064ffb3dae62d55932da54b31cb6c86",
      "url": "https://files.pythonhosted.org/packages/04/4b/29cac41a4d98d144bf5f6d33995617b185d14b22401f75ca86f384e87ff1/h11-0.16.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.8",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "httpcore",
    "version": "1.0.9",
    "wheel": {
      "bytes": 78784,
      "core_metadata_sha256": "fe2d4fda6199128978779e0cf27f3c045c531863fcdd987eacc74f3a18d41c21",
      "filename": "httpcore-1.0.9-py3-none-any.whl",
      "requires_python": ">=3.8",
      "sha256": "2d400746a40668fc9dec9810239072b40b4484b640a8c38fd654a024c7a1bf55",
      "url": "https://files.pythonhosted.org/packages/7e/f5/f66802a942d491edb555dd61e3a9961140fd64c90bce1eafd741609d334d/httpcore-1.0.9-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.8",
    "requires_dist_applicable": [
      "certifi",
      "h11>=0.16"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: BSD License"
      ],
      "expression": "BSD-3-Clause",
      "legacy": null
    }
  },
  {
    "name": "httpx",
    "version": "0.28.1",
    "wheel": {
      "bytes": 73517,
      "core_metadata_sha256": "febb9b0f8f3e80d57c8199c304f35c4336e8581d1d18d7983c92766b82793b25",
      "filename": "httpx-0.28.1-py3-none-any.whl",
      "requires_python": ">=3.8",
      "sha256": "d909fcccc110f8c7faf814ca82a9a4d816bc5a6dbfea25d6591d6985b8ba59ad",
      "url": "https://files.pythonhosted.org/packages/2a/39/e50c7c3a983047577ee07d2a9e53faf5a69493943ec3f6a384bdc792deb2/httpx-0.28.1-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.8",
    "requires_dist_applicable": [
      "anyio",
      "certifi",
      "httpcore==1.*",
      "idna"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: BSD License"
      ],
      "expression": null,
      "legacy": "BSD-3-Clause"
    }
  },
  {
    "name": "idna",
    "version": "3.19",
    "wheel": {
      "bytes": 68550,
      "core_metadata_sha256": "4d113161aca8582e8d28fddf3ea50f19b607209c2b3e4364379a163454680084",
      "filename": "idna-3.19-py3-none-any.whl",
      "requires_python": ">=3.9",
      "sha256": "815e7be7a7806d54abb586dc943addc79e8b2ee16915059658cbeff4b1b43bf4",
      "url": "https://files.pythonhosted.org/packages/57/b0/0e52c878c53f245edd3a11020f20979b3f490f245af532c7cae3027754b5/idna-3.19-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.9",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "BSD-3-Clause",
      "legacy": null
    }
  },
  {
    "name": "ja-ginza",
    "version": "5.2.0",
    "wheel": {
      "bytes": 59112919,
      "core_metadata_sha256": "7a593437e6ee3265bcce105a3d665c4bc7331bec133069f139d9f5a38128d801",
      "filename": "ja_ginza-5.2.0-py3-none-any.whl",
      "requires_python": null,
      "sha256": "c31a2ac57a7c2a1440f7e58111e37306c20dfaf08fd5a3f6f065948ff126cb30",
      "url": "https://files.pythonhosted.org/packages/f0/f8/d1bbc8bd545e61cacb7c0f0fedcfc041e2853e573ec4825136a8bd85e586/ja_ginza-5.2.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": null,
    "requires_dist_applicable": [
      "spacy<4.0.0,>=3.4.4",
      "sudachipy<0.7.0,>=0.6.2",
      "sudachidict-core>=20210802",
      "ginza<5.3.0,>=5.2.0"
    ],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": null,
      "legacy": "MIT License"
    }
  },
  {
    "name": "jinja2",
    "version": "3.1.6",
    "wheel": {
      "bytes": 134899,
      "core_metadata_sha256": "68c5548fb67c4132a13898d9b31ec50c6bea2abdd915d921f214355c3a6499c8",
      "filename": "jinja2-3.1.6-py3-none-any.whl",
      "requires_python": ">=3.7",
      "sha256": "85ece4451f492d0c13c5dd7c13a64681a86afae63a5f347908daf103ce6d2f67",
      "url": "https://files.pythonhosted.org/packages/62/a1/3d680cbfd5f4b8f15abc1d571870c5fc3e594bb582bc3b64ea099db13e56/jinja2-3.1.6-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.7",
    "requires_dist_applicable": [
      "MarkupSafe>=2.0"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: BSD License"
      ],
      "expression": null,
      "legacy": null
    }
  },
  {
    "name": "markdown-it-py",
    "version": "4.2.0",
    "wheel": {
      "bytes": 91687,
      "core_metadata_sha256": "72c36ff516755443b1ecb61e17b2567a990230b49a504b0eb0c42d5f82448a9c",
      "filename": "markdown_it_py-4.2.0-py3-none-any.whl",
      "requires_python": ">=3.10",
      "sha256": "9f7ebbcd14fe59494226453aed97c1070d83f8d24b6fc3a3bcf9a38092641c4a",
      "url": "https://files.pythonhosted.org/packages/b3/81/4da04ced5a082363ecfa159c010d200ecbd959ae410c10c0264a38cac0f5/markdown_it_py-4.2.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.10",
    "requires_dist_applicable": [
      "mdurl~=0.1"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": null
    }
  },
  {
    "name": "markupsafe",
    "version": "3.0.3",
    "wheel": {
      "bytes": 22947,
      "core_metadata_sha256": "12b4cc61a7fa288cf7667ee3f213786d9619db57fb33ff6f934afbcb5c12ec81",
      "filename": "markupsafe-3.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
      "requires_python": ">=3.9",
      "sha256": "d6dd0be5b5b189d31db7cda48b91d7e0a9795f31430b7f271219ab30f1d3ac9d",
      "url": "https://files.pythonhosted.org/packages/3c/2e/8d0c2ab90a8c1d9a24f0399058ab8519a3279d1bd4289511d74e909f060e/markupsafe-3.0.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_28_x86_64.whl",
      "yanked": false
    },
    "requires_python": ">=3.9",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "BSD-3-Clause",
      "legacy": null
    }
  },
  {
    "name": "mdurl",
    "version": "0.1.2",
    "wheel": {
      "bytes": 9979,
      "core_metadata_sha256": "b53b29d48f499367053fda3c81e7ce27d2558380ebbf83e66023b02eb7ddd25d",
      "filename": "mdurl-0.1.2-py3-none-any.whl",
      "requires_python": ">=3.7",
      "sha256": "84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8",
      "url": "https://files.pythonhosted.org/packages/b3/38/89ba8ad64ae25be8de66a6d463314cf1eb366222074cfda9ee839c56a4b4/mdurl-0.1.2-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.7",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": ""
    }
  },
  {
    "name": "murmurhash",
    "version": "1.0.15",
    "wheel": {
      "bytes": 134088,
      "core_metadata_sha256": "e3b1f1ffa44da7ce73e64ece028991d1c9c52b5d466b2586575ea822a03dfd6e",
      "filename": "murmurhash-1.0.15-cp312-cp312-manylinux1_x86_64.manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_5_x86_64.whl",
      "requires_python": "<3.15,>=3.6",
      "sha256": "5a301decfaccfec70fe55cb01dde2a012c3014a874542eaa7cc73477bb749616",
      "url": "https://files.pythonhosted.org/packages/ff/30/ea8f601a9bf44db99468696efd59eb9cff1157cd55cb586d67116697583f/murmurhash-1.0.15-cp312-cp312-manylinux1_x86_64.manylinux2014_x86_64.manylinux_2_17_x86_64.manylinux_2_5_x86_64.whl",
      "yanked": false
    },
    "requires_python": "<3.15,>=3.6",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "numpy",
    "version": "2.5.2",
    "wheel": {
      "bytes": 16722264,
      "core_metadata_sha256": "9a895d801184d2176f926af84eb47f2db1af2756afac99d64a2bf482d5d5e024",
      "filename": "numpy-2.5.2-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl",
      "requires_python": ">=3.12",
      "sha256": "3cdec01fa790a186d430433fdd4d4ffb70eed6f0eeb4bf05c8dbe2dce0a9bcb8",
      "url": "https://files.pythonhosted.org/packages/3a/5f/62d28cf019460c7f1394105b4d49d9911a9c444cb77ab0bd95a204c5a6de/numpy-2.5.2-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl",
      "yanked": false
    },
    "requires_python": ">=3.12",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0",
      "legacy": null
    }
  },
  {
    "name": "packaging",
    "version": "26.3",
    "wheel": {
      "bytes": 129956,
      "core_metadata_sha256": "70fdb89fc4d4a9a043bf7372b8972bcc883fddff34ab55e9cf80d73875384763",
      "filename": "packaging-26.3-py3-none-any.whl",
      "requires_python": ">=3.9",
      "sha256": "d7193f7c8e4e93f444fde0262bf90af30e16fa0ad0ad44cb553c87339b23cd1c",
      "url": "https://files.pythonhosted.org/packages/63/34/ba1c580383c9eada3711951fef0795c80b829a078d72188184bcab9dd527/packaging-26.3-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.9",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "Apache-2.0 OR BSD-2-Clause",
      "legacy": null
    }
  },
  {
    "name": "preshed",
    "version": "3.0.13",
    "wheel": {
      "bytes": 868988,
      "core_metadata_sha256": "52df36fb1dc14a7d67da1bf440d7198214c688b53a571da0a443d531b387eb88",
      "filename": "preshed-3.0.13-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "requires_python": "<3.15,>=3.9",
      "sha256": "8b8de3f58043070a354477995acdd98626ce43e4193c708ebd0f694e467f5155",
      "url": "https://files.pythonhosted.org/packages/51/94/8c9bc48a6ea4903f53a1a0031ce8e35687526949f25821762ef21493c007/preshed-3.0.13-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "yanked": false
    },
    "requires_python": "<3.15,>=3.9",
    "requires_dist_applicable": [
      "cymem<2.1.0,>=2.0.2",
      "murmurhash<1.1.0,>=0.28.0"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "pydantic",
    "version": "2.13.4",
    "wheel": {
      "bytes": 472262,
      "core_metadata_sha256": "d1e56c3412492512fb6b59a9dfc25ab7af2a8204585cd7bca000513023133394",
      "filename": "pydantic-2.13.4-py3-none-any.whl",
      "requires_python": ">=3.9",
      "sha256": "45a282cde31d808236fd7ea9d919b128653c8b38b393d1c4ab335c62924d9aba",
      "url": "https://files.pythonhosted.org/packages/fd/7b/122376b1fd3c62c1ed9dc80c931ace4844b3c55407b6fb2d199377c9736f/pydantic-2.13.4-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.9",
    "requires_dist_applicable": [
      "annotated-types>=0.6.0",
      "pydantic-core==2.46.4",
      "typing-extensions>=4.14.1",
      "typing-inspection>=0.4.2"
    ],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "MIT",
      "legacy": null
    }
  },
  {
    "name": "pydantic-core",
    "version": "2.46.4",
    "wheel": {
      "bytes": 2094516,
      "core_metadata_sha256": "135fa8b2f89473e9191c7078c2164e3ec6c8927a61c2379c2fddcc07f11f3bae",
      "filename": "pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
      "requires_python": ">=3.9",
      "sha256": "926c9541b14b12b1681dca8a0b75feb510b06c6341b70a8e500c2fdcff837cce",
      "url": "https://files.pythonhosted.org/packages/5f/97/2aab507d3d00ca626e8e57c1eac6a79e4e5fbcc63eb99733ff55d1717f65/pydantic_core-2.46.4-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl",
      "yanked": false
    },
    "requires_python": ">=3.9",
    "requires_dist_applicable": [
      "typing-extensions>=4.14.1"
    ],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "MIT",
      "legacy": null
    }
  },
  {
    "name": "pygments",
    "version": "2.21.0",
    "wheel": {
      "bytes": 1250147,
      "core_metadata_sha256": "1dde075570136774c706bf0009183a793fe0ee262e4a5590cc6eff8453eedd43",
      "filename": "pygments-2.21.0-py3-none-any.whl",
      "requires_python": ">=3.9",
      "sha256": "2363c69b61c4a97c838da3b130dcd6468f4848992b21a82f2a63ec34377137d9",
      "url": "https://files.pythonhosted.org/packages/71/46/17f022dd3e953bf20a04a028a21ec746d942f8d2af30fa0f124fa0e6a684/pygments-2.21.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.9",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "BSD-2-Clause",
      "legacy": null
    }
  },
  {
    "name": "requests",
    "version": "2.34.2",
    "wheel": {
      "bytes": 73075,
      "core_metadata_sha256": "8c384ba3e979480faae2859d3c5e6c1276dd2c3616e322e124d52c8cfc556f27",
      "filename": "requests-2.34.2-py3-none-any.whl",
      "requires_python": ">=3.10",
      "sha256": "2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0",
      "url": "https://files.pythonhosted.org/packages/a0/f4/c67b0b3f1b9245e8d266f0f112c500d50e5b4e83cb6f3b71b6528104182a/requests-2.34.2-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.10",
    "requires_dist_applicable": [
      "charset_normalizer<4,>=2",
      "idna<4,>=2.5",
      "urllib3<3,>=1.26",
      "certifi>=2023.5.7"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: Apache Software License"
      ],
      "expression": null,
      "legacy": "Apache-2.0"
    }
  },
  {
    "name": "rich",
    "version": "15.0.0",
    "wheel": {
      "bytes": 310654,
      "core_metadata_sha256": "fad34fc603fac4481bf81f8dd629492fc302c0ec31909c86644751512afb2e3b",
      "filename": "rich-15.0.0-py3-none-any.whl",
      "requires_python": ">=3.9.0",
      "sha256": "33bd4ef74232fb73fe9279a257718407f169c09b78a87ad3d296f548e27de0bb",
      "url": "https://files.pythonhosted.org/packages/82/3b/64d4899d73f91ba49a8c18a8ff3f0ea8f1c1d75481760df8c68ef5235bf5/rich-15.0.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.9.0",
    "requires_dist_applicable": [
      "markdown-it-py>=2.2.0",
      "pygments<3.0.0,>=2.13.0"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "setuptools",
    "version": "84.0.0",
    "wheel": {
      "bytes": 818216,
      "core_metadata_sha256": "3ef2975718dd31cabdd5829455e9b868ca14dbf79ed8fed2de0af4e87347006e",
      "filename": "setuptools-84.0.0-py3-none-any.whl",
      "requires_python": ">=3.10",
      "sha256": "51a52592b3b99e102b609654876bd65f19f999935166d1352678931132b0c670",
      "url": "https://files.pythonhosted.org/packages/95/9c/c510029fc6ef33a6275cd2c5d3cecd6613dfd6aa401d57c54f1c18852ccf/setuptools-84.0.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.10",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "MIT",
      "legacy": null
    }
  },
  {
    "name": "shellingham",
    "version": "1.5.4",
    "wheel": {
      "bytes": 9755,
      "core_metadata_sha256": "183d80220a37493262795739dd357cc5bb3f49bd390cc9198d5180e5451a07fa",
      "filename": "shellingham-1.5.4-py2.py3-none-any.whl",
      "requires_python": ">=3.7",
      "sha256": "7ecfff8f2fd72616f7481040475a65b2bf8af90a56c89140852d1120324e8686",
      "url": "https://files.pythonhosted.org/packages/e0/f9/0595336914c5619e5f28a1fb793285925a8cd4b432c9da0a987836c7f822/shellingham-1.5.4-py2.py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.7",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: ISC License (ISCL)"
      ],
      "expression": null,
      "legacy": "ISC License"
    }
  },
  {
    "name": "smart-open",
    "version": "8.0.1",
    "wheel": {
      "bytes": 73504,
      "core_metadata_sha256": "794b2eb5b9b5b7588de7325d808b5f819c2fc2f5d3299643f3469309c2f7bef9",
      "filename": "smart_open-8.0.1-py3-none-any.whl",
      "requires_python": "<4.0,>=3.10",
      "sha256": "3e97f90e92a952cb57863dfe132082c400a52eeeb27c067692fb51dbcc5b0089",
      "url": "https://files.pythonhosted.org/packages/c3/96/325b8c507ccecc50421fecc0345a502ee6e4a44785af3c4e6ecbadad624a/smart_open-8.0.1-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": "<4.0,>=3.10",
    "requires_dist_applicable": [
      "wrapt"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": null
    }
  },
  {
    "name": "spacy",
    "version": "3.8.15",
    "wheel": {
      "bytes": 32695414,
      "core_metadata_sha256": "07e7b27ec4fda84e10f690b063b043fb75a2b821ac3401104e816500e891d223",
      "filename": "spacy-3.8.15-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl",
      "requires_python": "<3.15,>=3.9",
      "sha256": "fa9df68fc8887c0a6440b84d1d307980e594d99b45f19a37d733e58caa9a6682",
      "url": "https://files.pythonhosted.org/packages/49/3d/88004d9518c912c30140e47f930abcbc9e7240d4c2aebe52c05b7f70df79/spacy-3.8.15-cp312-cp312-manylinux_2_24_x86_64.manylinux_2_28_x86_64.whl",
      "yanked": false
    },
    "requires_python": "<3.15,>=3.9",
    "requires_dist_applicable": [
      "spacy-legacy<3.1.0,>=3.0.11",
      "spacy-loggers<2.0.0,>=1.0.0",
      "murmurhash<1.1.0,>=0.28.0",
      "cymem<2.1.0,>=2.0.2",
      "preshed<3.1.0,>=3.0.2",
      "thinc<8.4.0,>=8.3.12",
      "wasabi<1.2.0,>=0.9.1",
      "srsly<3.0.0,>=2.5.3",
      "catalogue<2.1.0,>=2.0.6",
      "weasel<2.0.0,>=1.0.0",
      "confection<2.0.0,>=1.3.2",
      "typer<1.0.0,>=0.3.0",
      "click<9.0.0,>=8.2.1",
      "tqdm<5.0.0,>=4.38.0",
      "numpy>=1.19.0; python_version >= \"3.9\"",
      "requests<3.0.0,>=2.13.0",
      "pydantic<3.0.0,>=2.0.0",
      "jinja2",
      "setuptools",
      "packaging>=20.0"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "spacy-legacy",
    "version": "3.0.12",
    "wheel": {
      "bytes": 29971,
      "core_metadata_sha256": "d7d8fd88b4c1a701001877c575575049a22449481344d7e798b2637a2555dfd2",
      "filename": "spacy_legacy-3.0.12-py2.py3-none-any.whl",
      "requires_python": ">=3.6",
      "sha256": "476e3bd0d05f8c339ed60f40986c07387c0a71479245d6d0f4298dbd52cda55f",
      "url": "https://files.pythonhosted.org/packages/c3/55/12e842c70ff8828e34e543a2c7176dac4da006ca6901c9e8b43efab8bc6b/spacy_legacy-3.0.12-py2.py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.6",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "spacy-loggers",
    "version": "1.0.5",
    "wheel": {
      "bytes": 22343,
      "core_metadata_sha256": "18a091c9186a04bc9032859fd2ad3f853101ebe5aabff066391f0e584e692b73",
      "filename": "spacy_loggers-1.0.5-py3-none-any.whl",
      "requires_python": ">=3.6",
      "sha256": "196284c9c446cc0cdb944005384270d775fdeaf4f494d8e269466cfa497ef645",
      "url": "https://files.pythonhosted.org/packages/33/78/d1a1a026ef3af911159398c939b1509d5c36fe524c7b644f34a5146c4e16/spacy_loggers-1.0.5-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.6",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "srsly",
    "version": "2.5.3",
    "wheel": {
      "bytes": 1180873,
      "core_metadata_sha256": "9820d9aeff1394724211ce5cff45b122160a13f4888cdf23f11acf28a87b94d3",
      "filename": "srsly-2.5.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "requires_python": "<3.15,>=3.9",
      "sha256": "99026bcd9cbd3211cc36517400b04ca0fc5d3e412b14daf84ee6e65f67d9a2d8",
      "url": "https://files.pythonhosted.org/packages/4e/c9/741e29f534919a944a16da4184924b1d3404c4bf60716ab2b91be771d1e3/srsly-2.5.3-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "yanked": false
    },
    "requires_python": "<3.15,>=3.9",
    "requires_dist_applicable": [
      "catalogue<2.1.0,>=2.0.3"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "sudachidict-core",
    "version": "20260723",
    "wheel": {
      "bytes": 72275897,
      "core_metadata_sha256": "e102a6879ab09b732ce9b291aec71552a0cd0186df7e1d7eef99d737b4f40a12",
      "filename": "sudachidict_core-20260723-py3-none-any.whl",
      "requires_python": null,
      "sha256": "b3869ce6b12b4bfa09575dc19030703bb669ab41bac12a74cafcbb28c6be2498",
      "url": "https://files.pythonhosted.org/packages/46/fe/68a146fced55319af40d25a4fe19b94c3a988406ce4674a8b2f0237fbc9f/sudachidict_core-20260723-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": null,
    "requires_dist_applicable": [
      "SudachiPy<0.7,>=0.5"
    ],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": null,
      "legacy": "Apache-2.0"
    }
  },
  {
    "name": "sudachipy",
    "version": "0.6.11",
    "wheel": {
      "bytes": 1628277,
      "core_metadata_sha256": "46c993656ca7e4d78e433737b49eb7708d1eea67d0968176d210746724b288f9",
      "filename": "sudachipy-0.6.11-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "requires_python": null,
      "sha256": "9d024efea4ff8b5bd0709f1afbb8e8f230ebd4ec83f9cd76f47b0542b7c22e91",
      "url": "https://files.pythonhosted.org/packages/49/ee/f7c20d6e17619c83f5ffa3ed7bd1582174809fd8b396fb9250f24210dd57/sudachipy-0.6.11-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "yanked": false
    },
    "requires_python": null,
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": null,
      "legacy": "Apache-2.0"
    }
  },
  {
    "name": "thinc",
    "version": "8.3.13",
    "wheel": {
      "bytes": 3903307,
      "core_metadata_sha256": "151e4f7732eb618431031e5945aef62898bd729c32e2a28c8378af15809df1f0",
      "filename": "thinc-8.3.13-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "requires_python": "<3.15,>=3.10",
      "sha256": "4b5ec9ff313819e7d8667794a3559463fa89ff45aaa73e3fd8d6273b1e0d7a7f",
      "url": "https://files.pythonhosted.org/packages/f9/ff/6914bf370bd1d604d89e6dfb46b97d10cd9b00d42ff8c036283e92314a8c/thinc-8.3.13-cp312-cp312-manylinux2014_x86_64.manylinux_2_17_x86_64.whl",
      "yanked": false
    },
    "requires_python": "<3.15,>=3.10",
    "requires_dist_applicable": [
      "blis<1.4.0,>=1.3.0",
      "murmurhash<1.1.0,>=1.0.2",
      "cymem<2.1.0,>=2.0.2",
      "preshed<3.1.0,>=3.0.2",
      "wasabi<1.2.0,>=0.8.1",
      "srsly<3.1.0,>=2.4.0",
      "catalogue<2.1.0,>=2.0.4",
      "confection<2.0.0,>=1.1.0",
      "setuptools",
      "numpy<3.0.0,>=1.21.0",
      "pydantic<3.0.0,>=2.0.0",
      "packaging>=20.0"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "tqdm",
    "version": "4.70.0",
    "wheel": {
      "bytes": 80184,
      "core_metadata_sha256": "0d95b85b90428f8776afc4a92b17c5094f78ee98d150b3255acbcdf4e9d57941",
      "filename": "tqdm-4.70.0-py3-none-any.whl",
      "requires_python": ">=3.8",
      "sha256": "7f585706bfddbdebf89daac705b2dfcc16890130727d3197ca62c732b4310953",
      "url": "https://files.pythonhosted.org/packages/f9/1c/01bfd571a64e7f270e6bab5e33777debe0edc56759233ce84f27dec92d14/tqdm-4.70.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.8",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": null,
      "legacy": "MPL-2.0 AND MIT"
    }
  },
  {
    "name": "typer",
    "version": "0.27.1",
    "wheel": {
      "bytes": 122874,
      "core_metadata_sha256": "d71011dc4b250b9670d91fbae7882d707a9ef93b22a527d90992a962a5759601",
      "filename": "typer-0.27.1-py3-none-any.whl",
      "requires_python": ">=3.10",
      "sha256": "53150287edd11baeb4e4722c8e394fcdf8181c0ae89485cba8d25c778d5edd56",
      "url": "https://files.pythonhosted.org/packages/43/89/9518bc0c3929bee36b3a4a8e3daddd6e03f92f9961c66d4983b837160543/typer-0.27.1-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.10",
    "requires_dist_applicable": [
      "shellingham>=1.3.0",
      "rich>=13.8.0",
      "annotated-doc>=0.0.2"
    ],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "MIT",
      "legacy": null
    }
  },
  {
    "name": "typing-extensions",
    "version": "4.16.0",
    "wheel": {
      "bytes": 45571,
      "core_metadata_sha256": "b05084ca1d50879865178d9fff9fabeab61bdfb1f361bfbde95421ffc8f9be46",
      "filename": "typing_extensions-4.16.0-py3-none-any.whl",
      "requires_python": ">=3.9",
      "sha256": "481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8",
      "url": "https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.9",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "PSF-2.0",
      "legacy": null
    }
  },
  {
    "name": "typing-inspection",
    "version": "0.4.4",
    "wheel": {
      "bytes": 14750,
      "core_metadata_sha256": "bad3d9e6342ef6750cf5128ec942327b8bebdce0b6e4d6f67cb15b27ae5118da",
      "filename": "typing_inspection-0.4.4-py3-none-any.whl",
      "requires_python": ">=3.10",
      "sha256": "65b8397ba37ccbce054456aaccddfc91e6e3083c92824df348d96ca832f3f147",
      "url": "https://files.pythonhosted.org/packages/67/81/4add07e5172b7ac40d8ed5ff580409a7801a4fe26d529bdd915401dabfbe/typing_inspection-0.4.4-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.10",
    "requires_dist_applicable": [
      "typing-extensions>=4.15.0"
    ],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "MIT",
      "legacy": null
    }
  },
  {
    "name": "urllib3",
    "version": "2.7.0",
    "wheel": {
      "bytes": 131087,
      "core_metadata_sha256": "66147856d30bbb6bed01c6ce3326d0f48d84ed5f286ac177633a1486b82eace5",
      "filename": "urllib3-2.7.0-py3-none-any.whl",
      "requires_python": ">=3.10",
      "sha256": "9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897",
      "url": "https://files.pythonhosted.org/packages/7f/3e/5db95bcf282c52709639744ca2a8b149baccf648e39c8cc87553df9eae0c/urllib3-2.7.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.10",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "MIT",
      "legacy": null
    }
  },
  {
    "name": "wasabi",
    "version": "1.1.3",
    "wheel": {
      "bytes": 27880,
      "core_metadata_sha256": "428dba3283ea8a4059eff38495ac22d58f9c29b7c9ff12df3e796c209a96d069",
      "filename": "wasabi-1.1.3-py3-none-any.whl",
      "requires_python": ">=3.6",
      "sha256": "f76e16e8f7e79f8c4c8be49b4024ac725713ab10cd7f19350ad18a8e3f71728c",
      "url": "https://files.pythonhosted.org/packages/06/7c/34330a89da55610daa5f245ddce5aab81244321101614751e7537f125133/wasabi-1.1.3-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.6",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "weasel",
    "version": "1.0.0",
    "wheel": {
      "bytes": 50713,
      "core_metadata_sha256": "a16824512ee2fec38c83720e7c7f0fcbaabff69e047820953418088bf4adc6b0",
      "filename": "weasel-1.0.0-py3-none-any.whl",
      "requires_python": ">=3.7",
      "sha256": "89518acee027f49d743126c3502d35e6dd14f5768be5c37c9af47c171b6005cc",
      "url": "https://files.pythonhosted.org/packages/0a/07/57ebf7a6798b016c064bd0ca81b4c6a99daa4dc377b898bc7b41eb6b5af0/weasel-1.0.0-py3-none-any.whl",
      "yanked": false
    },
    "requires_python": ">=3.7",
    "requires_dist_applicable": [
      "confection>=1.0.0",
      "packaging>=20.0",
      "wasabi>=0.9.1",
      "srsly>=2.4.3",
      "typer>=0.3.0",
      "cloudpathlib>=0.7.0",
      "smart-open>=5.2.1",
      "httpx>=0.24.0",
      "pydantic>=2.0.0"
    ],
    "registry_licence_declarations": {
      "classifiers": [
        "License :: OSI Approved :: MIT License"
      ],
      "expression": null,
      "legacy": "MIT"
    }
  },
  {
    "name": "wrapt",
    "version": "2.3.0",
    "wheel": {
      "bytes": 172381,
      "core_metadata_sha256": "bed8a0620d9d2a6779427fcecabcbc642f6fa68b107ab583faa01a6dabcafaef",
      "filename": "wrapt-2.3.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl",
      "requires_python": ">=3.9",
      "sha256": "5d221a6e6ddd302b8397433184e96b59f259f50024b854db1c411a881586b6b8",
      "url": "https://files.pythonhosted.org/packages/28/7f/cfd9bc4b1f5e424eeea83d0493e43f3b1b02707ce8e50c47945873982bd5/wrapt-2.3.0-cp312-cp312-manylinux1_x86_64.manylinux_2_28_x86_64.manylinux_2_5_x86_64.whl",
      "yanked": false
    },
    "requires_python": ">=3.9",
    "requires_dist_applicable": [],
    "registry_licence_declarations": {
      "classifiers": [],
      "expression": "BSD-2-Clause",
      "legacy": null
    }
  }
]
'''

PLAC_VERSION = '1.4.7'
PLAC_SHA256 = '8af4bcd5d52e06c31fab641bffb7040d0eb0e579e2f70a4d2e87af5eed0612ea'
PACKAGING_VERSION = '26.3'
EXPECTED_NAMES = frozenset(r['name'] for r in json.loads(_FIXED_RECORDS_JSON)) | {'plac'}
SETUPTOOLS_PTH = (
    b"import os; var = 'SETUPTOOLS_USE_DISTUTILS'; enabled = os.environ.get(var, 'local') == 'local'; "
    b"enabled and __import__('_distutils_hack').add_shim(); \n"
)
SETUPTOOLS_PTH_SHA256 = '2638ce9e2500e572a5e0de7faed6661eb569d1b696fcba07b0dd223da5f5d224'
SETUPTOOLS_SHIM_SHA256 = 'ced72e54431ecf2d8d7dbd8a1e27724f1b171af3ca1503c304bf11c59a7fe861'
SETUPTOOLS_AUDIT = {
    'source_release_sha256': '68ac9892c7776482288c6c1ec01ec315aa70bbfdb202edecbf7980a09e20400b',
    'source_release': 'LunaTranslator-UI-Custom-v1.0.1-x64.zip',
    'version': '84.0.0',
    'metadata_sha256': '3ef2975718dd31cabdd5829455e9b868ca14dbf79ed8fed2de0af4e87347006e',
    'pth_sha256': SETUPTOOLS_PTH_SHA256,
    'shim_sha256': SETUPTOOLS_SHIM_SHA256,
    'review': 'Static bytes only: environment-gated installation of DistutilsMetaFinder in sys.meta_path; nothing executed.',
    'official_wheel_comparison': 'PENDING: future exact official-wheel SHA and embedded byte comparisons must all pass before allowance.',
}


class WheelValidationError(ValueError):
    """Fail-closed blocker with a finite public label independent of its message."""

    def __init__(self, message, *, subcheck='unclassified', observed_metadata_version=None):
        super().__init__(message)
        self.subcheck = subcheck if type(subcheck) is str and subcheck in WHEEL_SUBCHECKS else 'unclassified'
        self.observed_metadata_version = None
        if self.subcheck == 'metadata_version_unsupported':
            self.observed_metadata_version = (observed_metadata_version
                if type(observed_metadata_version) is str and observed_metadata_version in METADATA_VERSION_OBSERVATIONS
                else 'other')


@dataclass(frozen=True)
class Limits:
    archive_bytes: int = 256 * 1024 * 1024
    total_archive_bytes: int = 512 * 1024 * 1024
    central_directory_bytes: int = 16 * 1024 * 1024
    members: int = 50000
    member_bytes: int = 512 * 1024 * 1024
    wheel_uncompressed_bytes: int = 1024 * 1024 * 1024
    total_uncompressed_bytes: int = 2 * 1024 * 1024 * 1024
    metadata_bytes: int = 2 * 1024 * 1024
    record_bytes: int = 16 * 1024 * 1024
    compression_ratio: int = 1000


DEFAULT_LIMITS = Limits()


@dataclass(frozen=True)
class VerifiedMember:
    archive_path: str
    destination: str  # Relative to site-packages, never an absolute OS path.
    size: int
    sha256: str
    directory: bool
    relocated: bool


@dataclass(frozen=True)
class VerifiedWheel:
    name: str
    version: str
    filename: str
    path: str
    sha256: str
    size: int
    uncompressed_bytes: int
    metadata_sha256: str
    requirements: tuple[str, ...]
    applicable_requirements: tuple[str, ...]
    provides_extras: tuple[str, ...]
    members: tuple[VerifiedMember, ...]
    declared_license_files: tuple[str, ...]
    license_expression: str | None
    legacy_license: str | None
    startup_hook: str | None


@dataclass(frozen=True)
class ValidationReport:
    wheels: tuple[VerifiedWheel, ...]
    dependency_edges: tuple[tuple[str, str, str], ...]
    total_archive_bytes: int
    total_uncompressed_bytes: int
    packaging_version: str
    notice_policy: str = 'Retain every member and declared notice; no legal-clearance claim.'

    def to_dict(self) -> dict:
        return asdict(self)


def _fail(message: str, *, subcheck: str, observed_metadata_version=None) -> None:
    raise WheelValidationError(message, subcheck=subcheck, observed_metadata_version=observed_metadata_version)


def _sha256(value: object, label: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{64}', value):
        _fail(f'{label}: expected lowercase SHA256', subcheck='pin_sha256_invalid')
    return value


def _positive_int(value: object, label: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= maximum:
        _fail(f'{label}: expected positive bounded integer', subcheck='pin_size_invalid')
    return value


def _requirement(value: str) -> Requirement:
    try:
        result = Requirement(value)
    except (InvalidRequirement, TypeError) as error:
        _fail(f'Invalid dependency requirement: {error}', subcheck='dependency_requirement_invalid')
    if result.url is not None:
        _fail('Direct-URL dependencies are outside the fixed wheel closure', subcheck='dependency_direct_url_forbidden')
    return result


def _requirement_key(value: str) -> tuple:
    requirement = _requirement(value)
    return (canonicalize_name(requirement.name), tuple(sorted(requirement.extras)),
            str(requirement.specifier), str(requirement.marker or ''))


def validate_manifest(manifest: dict) -> dict[str, dict]:
    """Check frozen identity of all 49 records; return a detached name mapping.

    Expected manifest shape is {'records': [...]} using the reviewed proposal's
    record shape. All original 48 records' pinned fields must be unchanged. The
    supplied final plac record must be 1.4.7 with the mandated SHA, exact non-yanked
    filename/URL/size, and explicit dependency/python declarations. This function
    does not establish whether the manifest has received external authorization.
    """
    if not isinstance(manifest, dict) or not isinstance(manifest.get('records'), list):
        _fail('Manifest requires a records list', subcheck='manifest_records_missing')
    if len(manifest['records']) != 49:
        _fail('Manifest must contain exactly 49 wheels', subcheck='manifest_count_mismatch')
    fixed = {r['name']: r for r in json.loads(_FIXED_RECORDS_JSON)}
    normalized = {}
    for record in manifest['records']:
        if not isinstance(record, dict) or not isinstance(record.get('name'), str):
            _fail('Invalid manifest record', subcheck='manifest_record_invalid')
        name = canonicalize_name(record['name'])
        if name in normalized or name not in EXPECTED_NAMES or name != record['name']:
            _fail('Manifest contains an unknown, duplicate or noncanonical package name', subcheck='manifest_package_identity_invalid')
        version = record.get('version')
        wheel = record.get('wheel')
        if not isinstance(version, str) or not isinstance(wheel, dict):
            _fail(f'{name}: version and wheel identity required', subcheck='manifest_wheel_identity_missing')
        try:
            parsed_name, parsed_version, _, _ = parse_wheel_filename(wheel['filename'])
        except (KeyError, TypeError, InvalidWheelFilename) as error:
            _fail(f'{name}: invalid wheel filename: {error}', subcheck='manifest_filename_invalid')
        if parsed_name != name or str(parsed_version) != version or '/' in wheel['filename'] or '\\' in wheel['filename']:
            _fail(f'{name}: filename identity mismatch', subcheck='manifest_filename_identity_mismatch')
        _sha256(wheel.get('sha256'), f'{name} wheel')
        _positive_int(wheel.get('bytes'), f'{name} wheel bytes', DEFAULT_LIMITS.archive_bytes)
        if wheel.get('yanked') is not False:
            _fail(f'{name}: yanked or unspecified yank status', subcheck='manifest_yank_status_invalid')
        parsed_url = urlparse(wheel.get('url', ''))
        if (parsed_url.scheme != 'https' or parsed_url.netloc != 'files.pythonhosted.org'
                or parsed_url.params or parsed_url.query or parsed_url.fragment
                or unquote(parsed_url.path.rsplit('/', 1)[-1]) != wheel['filename']):
            _fail(f'{name}: invalid finalized wheel URL', subcheck='manifest_url_invalid')
        if 'requires_python' not in record or 'requires_python' not in wheel:
            _fail(f'{name}: explicit Requires-Python declaration missing', subcheck='manifest_requires_python_missing')
        if record['requires_python'] != wheel['requires_python']:
            _fail(f'{name}: conflicting Requires-Python declarations', subcheck='manifest_requires_python_conflict')
        if record['requires_python'] is not None and not isinstance(record['requires_python'], str):
            _fail(f'{name}: invalid Requires-Python declaration', subcheck='manifest_requires_python_type_invalid')
        try:
            SpecifierSet(record['requires_python'] or '')
        except InvalidSpecifier as error:
            _fail(f'{name}: invalid Requires-Python: {error}', subcheck='manifest_requires_python_invalid')
        requirements = record.get('requires_dist_applicable')
        if not isinstance(requirements, list) or any(not isinstance(x, str) for x in requirements):
            _fail(f'{name}: explicit applicable dependency list required', subcheck='manifest_dependency_list_invalid')
        for requirement in requirements:
            _requirement(requirement)
        if name == 'plac':
            if version != PLAC_VERSION or wheel['sha256'] != PLAC_SHA256:
                _fail('plac must be exactly 1.4.7 with the mandated SHA256; no fallback', subcheck='manifest_plac_pin_mismatch')
            if requirements:
                _fail('plac 1.4.7 must not add dependencies to the reviewed fixed closure', subcheck='manifest_plac_dependencies_forbidden')
            metadata_hash = wheel.get('core_metadata_sha256')
            if metadata_hash is not None:
                _sha256(metadata_hash, 'plac core metadata')
        else:
            for key in ('version', 'wheel', 'requires_python', 'requires_dist_applicable', 'registry_licence_declarations'):
                if record.get(key) != fixed[name][key]:
                    _fail(f'{name}: frozen {key} changed', subcheck='manifest_frozen_field_changed')
        normalized[name] = json.loads(json.dumps(record))
    if set(normalized) != EXPECTED_NAMES:
        _fail('Manifest does not equal the fixed 49-package closure', subcheck='manifest_closure_mismatch')
    return normalized


def validate_finalized_manifest(data: bytes) -> dict[str, dict]:
    """Bind the final collected bytes, then attach the frozen dependency graph.

    The final metadata artifact's `files` schema preserves all49 wheel/licence
    records but omits the already reviewed requirement edges. No version or
    requirement is resolved here; the old48 source snapshot supplies those fixed
    edges, and the reviewed plac1.4.7 record has no requirements.
    """
    from finalized_manifest import read_finalized_manifest
    final = read_finalized_manifest(data)
    fixed = {record['name']: record for record in json.loads(_FIXED_RECORDS_JSON)}
    records = []
    for record in final['files']:
        name = record['name']
        graph = {'requires_python': record['wheel']['requires_python'], 'requires_dist_applicable': []}
        if name != 'plac':
            graph = {key: fixed[name][key] for key in ('requires_python', 'requires_dist_applicable')}
        records.append({**record, **graph})
    return validate_manifest({'records': records})


def validate_runtime(marker_environment: dict[str, str], supported_tags) -> tuple[dict[str, str], frozenset]:
    """Require a complete explicit CPython 3.12.14/Linux/x86_64 marker context."""
    required = {
        'implementation_name', 'implementation_version', 'os_name', 'platform_machine',
        'platform_release', 'platform_system', 'platform_version', 'python_full_version',
        'platform_python_implementation', 'python_version', 'sys_platform',
    }
    if (not isinstance(marker_environment, dict) or set(marker_environment) != required
            or any(not isinstance(v, str) for v in marker_environment.values())):
        _fail('Provide all 11 explicit runtime marker fields, with no implicit host defaults', subcheck='runtime_marker_shape_invalid')
    fixed = {'implementation_name': 'cpython', 'implementation_version': '3.12.14',
             'os_name': 'posix', 'platform_machine': 'x86_64', 'platform_system': 'Linux',
             'python_full_version': '3.12.14', 'platform_python_implementation': 'CPython',
             'python_version': '3.12', 'sys_platform': 'linux'}
    if any(marker_environment[key] != value for key, value in fixed.items()):
        _fail('Runtime must be the fixed CPython 3.12.14 Linux x86_64 target', subcheck='runtime_identity_mismatch')
    if not marker_environment['platform_release'] or not marker_environment['platform_version']:
        _fail('Runtime release/version observations must not be blank', subcheck='runtime_observations_missing')
    if isinstance(supported_tags, (str, bytes)):
        _fail('supported_tags must be an explicit nonempty sequence', subcheck='runtime_tags_shape_invalid')
    try:
        tags = frozenset(tag for value in supported_tags for tag in parse_tag(str(value)))
    except (TypeError, ValueError) as error:
        _fail(f'Invalid supported tags: {error}', subcheck='runtime_tags_invalid')
    if not tags or not any(t.interpreter == 'cp312' and t.abi == 'cp312' and t.platform.endswith('_x86_64') for t in tags):
        _fail('Actual target-supported cp312/cp312 Linux x86_64 tags are required', subcheck='runtime_target_tag_missing')
    return dict(marker_environment), tags


def _safe_path(name: str, *, directory: bool = False) -> str:
    if not isinstance(name, str) or not name or len(name.encode('utf-8')) > 4096:
        _fail('Unsafe or overlong archive path', subcheck='member_path_size_invalid')
    if '\\' in name or ':' in name or name.startswith('/') or '\x00' in name:
        _fail(f'Unsafe archive path: {name!r}', subcheck='member_path_unsafe')
    if any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in name) or unicodedata.normalize('NFC', name) != name:
        _fail('Archive path contains controls or noncanonical Unicode', subcheck='member_path_unicode_invalid')
    path = name[:-1] if directory and name.endswith('/') else name
    parts = path.split('/')
    if any(p in ('', '.', '..') or p.endswith((' ', '.')) or len(p.encode('utf-8')) > 255 for p in parts):
        _fail(f'Unsafe archive path components: {name!r}', subcheck='member_path_components_unsafe')
    return path


def _mapped_destination(name: str, wheel_base: str, directory: bool) -> str | None:
    clean = _safe_path(name, directory=directory)
    parts = clean.split('/')
    if not parts[0].endswith('.data'):
        return clean
    if parts[0] != wheel_base + '.data':
        _fail('Wheel contains a foreign .data relocation root', subcheck='layout_foreign_data_root')
    if len(parts) == 1:
        if directory:
            return None
        _fail('.data root must be a directory', subcheck='layout_data_root_not_directory')
    if parts[1] not in ('purelib', 'platlib'):
        _fail(f'Unsupported legitimate .data relocation category {parts[1]!r}: explicit installation scheme review required', subcheck='layout_relocation_scheme_unsupported')
    if len(parts) == 2:
        if directory:
            return None
        _fail('.data scheme root must be a directory', subcheck='layout_scheme_root_not_directory')
    return '/'.join(parts[2:])


def _check_collisions(entries) -> None:
    seen = {}
    for path, directory in entries:
        key = path.casefold()
        if key in seen:
            _fail(f'Duplicate/casefold-colliding path: {path}', subcheck='layout_duplicate_or_casefold_collision')
        seen[key] = directory
    for path, _ in entries:
        parts = path.casefold().split('/')
        for i in range(1, len(parts)):
            parent = '/'.join(parts[:i])
            if parent in seen and not seen[parent]:
                _fail(f'File/directory collision: {path}', subcheck='layout_file_directory_collision')


def _zip_preflight(stream, size: int, limits: Limits) -> None:
    if size < 22 or size > limits.archive_bytes:
        _fail('Wheel size exceeds archive bounds', subcheck='zip_archive_size_limit')
    stream.seek(0)
    if stream.read(4) != b'PK\x03\x04':
        _fail('Wheel must be an ordinary ZIP without a prepended payload', subcheck='zip_preamble_invalid')
    stream.seek(size - 22)
    end = stream.read(22)
    if end[:4] != b'PK\x05\x06':
        _fail('Unsupported ZIP comment/trailing bytes/ZIP64: explicit archive review required', subcheck='zip_end_record_unsupported')
    _, disk, directory_disk, disk_entries, entries, central_size, central_offset, comment = struct.unpack('<4s4H2IH', end)
    if disk or directory_disk or disk_entries != entries or comment or entries == 0xffff or central_size == 0xffffffff or central_offset == 0xffffffff:
        _fail('Multi-disk or ZIP64 archive is not supported', subcheck='zip_multidisk_or_zip64_unsupported')
    if not 1 <= entries <= limits.members or central_size > limits.central_directory_bytes:
        _fail('ZIP central directory exceeds bounded limits', subcheck='zip_directory_limit')
    if central_offset + central_size != size - 22:
        _fail('ZIP central directory boundary mismatch', subcheck='zip_directory_boundary_mismatch')
    stream.seek(0)


def _header(message, key: str, required: bool = False) -> str | None:
    values = message.get_all(key, [])
    if len(values) > 1 or (required and len(values) != 1):
        _fail(f'Duplicate or missing {key} metadata header', subcheck='metadata_header_cardinality')
    return str(values[0]) if values else None


def _parse_headers(data: bytes, label: str):
    try:
        data.decode('utf-8', errors='strict')
        message = BytesParser(policy=policy.default).parsebytes(data)
    except (UnicodeError, ValueError) as error:
        _fail(f'{label}: invalid UTF-8 metadata: {error}', subcheck='metadata_encoding_invalid')
    if message.defects or message.is_multipart():
        _fail(f'{label}: malformed metadata', subcheck='metadata_parse_invalid')
    return message


# Core Metadata through 2.4, including documented deprecated fields. Dynamic
# names core metadata fields, not pyproject keys or normalized distribution names.
# https://packaging.python.org/en/latest/specifications/core-metadata/
# https://peps.python.org/pep-0643/#specification
_CORE_SINGLETON_FIELDS = frozenset({
    'metadata-version', 'name', 'version', 'summary', 'description',
    'description-content-type', 'keywords', 'home-page', 'download-url',
    'author', 'author-email', 'maintainer', 'maintainer-email', 'license',
    'license-expression', 'requires-python',
})
_CORE_MULTIPLE_FIELDS = frozenset({
    'dynamic', 'platform', 'supported-platform', 'classifier', 'requires-dist',
    'requires-external', 'project-url', 'provides-extra', 'provides-dist',
    'obsoletes-dist', 'requires', 'provides', 'obsoletes', 'license-file',
})
_DYNAMIC_FORBIDDEN_FIELDS = frozenset({'name', 'version', 'metadata-version', 'dynamic'})
_DYNAMIC_FIELDS_24 = (_CORE_SINGLETON_FIELDS | _CORE_MULTIPLE_FIELDS) - _DYNAMIC_FORBIDDEN_FIELDS
_DYNAMIC_FIELDS_22_23 = _DYNAMIC_FIELDS_24 - {'license-expression', 'license-file'}
_DYNAMIC_FIELDS_BY_VERSION = {
    '2.2': _DYNAMIC_FIELDS_22_23,
    '2.3': _DYNAMIC_FIELDS_22_23,
    '2.4': _DYNAMIC_FIELDS_24,
}


def _validate_dynamic_metadata(message, metadata_version: str) -> None:
    """Validate structure without weakening any final wheel-value check.

    Dynamic in a prebuilt wheel is informational. Its optional target may be
    absent and valid repeated declarations are permitted. No sdist is available
    here, so no cross-artifact equivalence is inferred. Original bytes remain
    hash-bound and retained; only declaration comparison uses normalized names.
    """
    for field in sorted(_CORE_SINGLETON_FIELDS):
        _header(message, field, required=field in {'name', 'version', 'metadata-version'})
    values = [value for name, value in message.raw_items() if name.lower() == 'dynamic']
    if not values:
        return
    allowed = _DYNAMIC_FIELDS_BY_VERSION.get(metadata_version)
    if allowed is None:
        _fail('Dynamic requires a supported metadata format introduced in 2.2',
              subcheck='metadata_dynamic_version_unsupported')
    for raw in values:
        # Unfold ordinary email header continuation whitespace, then trim only
        # ASCII SP/HTAB. Raw values prevent encoded words from hiding bad tokens.
        value = re.sub(r'\r?\n[ \t]+', ' ', raw).strip(' \t')
        if not re.fullmatch(r'[A-Za-z]+(?:-[A-Za-z]+)*', value, flags=re.ASCII):
            _fail('Dynamic must name one ASCII core metadata field',
                  subcheck='metadata_dynamic_field_malformed')
        field = value.lower()
        if field in _DYNAMIC_FORBIDDEN_FIELDS:
            _fail('Dynamic names an immutable or self-referential metadata field',
                  subcheck='metadata_dynamic_field_forbidden')
        if field not in allowed:
            _fail('Dynamic names a field outside this supported metadata version',
                  subcheck='metadata_dynamic_field_unsupported')


def _applicable(requirements, environment, extras=('',)) -> tuple[str, ...]:
    selected = []
    for raw in requirements:
        requirement = _requirement(raw)
        try:
            applies = requirement.marker is None or any(
                requirement.marker.evaluate({**environment, 'extra': extra}) for extra in extras)
        except (KeyError, ValueError) as error:
            _fail(f'Cannot evaluate dependency marker explicitly: {error}', subcheck='dependency_marker_invalid')
        if applies:
            selected.append(raw)
    return tuple(selected)


def _validate_wheel(path: Path, record: dict, environment: dict, tags: frozenset,
                    limits: Limits = DEFAULT_LIMITS) -> VerifiedWheel:
    """Internal archive primitive; production callers use validate_wheelhouse."""
    wheel = record['wheel']
    if path.name != wheel['filename']:
        _fail('Wheel path basename does not equal the exact pinned filename', subcheck='archive_filename_mismatch')
    try:
        initial = path.lstat()
    except OSError as error:
        _fail(f'Cannot inspect wheel: {error}', subcheck='archive_stat_failed')
    if not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
        _fail('Wheel input must be a regular file with no symlink/hardlink aliases', subcheck='archive_file_type_invalid')
    if initial.st_size != wheel['bytes']:
        _fail('Wheel byte size does not match the pin', subcheck='archive_size_pin_mismatch')
    _, _, _, filename_tags = parse_wheel_filename(path.name)
    if not filename_tags & tags:
        _fail('Pinned wheel is not compatible with the observed runtime tags', subcheck='archive_runtime_tag_mismatch')
    wheel_base = path.name.split('-')[0] + '-' + path.name.split('-')[1]
    dist_info = wheel_base + '.dist-info'
    record_path = dist_info + '/RECORD'
    metadata_path = dist_info + '/METADATA'
    wheel_path = dist_info + '/WHEEL'
    metadata_blobs = {}
    digests = {}
    inventory = []
    total = 0
    hook = None
    open_flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0)
    try:
        fd = os.open(path, open_flags)
    except OSError as error:
        _fail(f'Cannot open wheel safely: {error}', subcheck='archive_open_failed')
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size) != (initial.st_dev, initial.st_ino, initial.st_size):
            _fail('Wheel changed during validation', subcheck='archive_changed')
        _zip_preflight(stream, before.st_size, limits)
        actual_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual_hash != wheel['sha256']:
            _fail('Wheel SHA256 does not match the exact pin', subcheck='archive_sha256_pin_mismatch')
        stream.seek(0)
        try:
            with zipfile.ZipFile(stream) as archive:
                infos = archive.infolist()
                if len(infos) > limits.members:
                    _fail('ZIP member count exceeds bound', subcheck='zip_member_count_limit')
                source_entries = []
                destination_entries = []
                for info in infos:
                    if info.orig_filename != info.filename:
                        _fail('Truncated/null-bearing ZIP filename', subcheck='zip_filename_truncated')
                    directory = info.is_dir()
                    safe = _safe_path(info.filename, directory=directory)
                    mode = info.external_attr >> 16
                    kind = stat.S_IFMT(mode)
                    if kind not in (0, stat.S_IFDIR if directory else stat.S_IFREG):
                        _fail('ZIP contains a symlink, device, or other nonregular member', subcheck='zip_member_type_invalid')
                    if mode & (stat.S_ISUID | stat.S_ISGID | stat.S_ISVTX):
                        _fail('ZIP member has special permission bits', subcheck='zip_member_permission_invalid')
                    if info.flag_bits & (1 | 64) or info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                        _fail('Encrypted or unsupported ZIP compression', subcheck='zip_encryption_or_compression_unsupported')
                    if info.file_size > limits.member_bytes or (directory and info.file_size):
                        _fail('ZIP member exceeds limits or directory has content', subcheck='zip_member_size_limit')
                    if info.file_size > max(1024 * 1024, info.compress_size * limits.compression_ratio):
                        _fail('ZIP decompression ratio exceeds bound', subcheck='zip_compression_ratio_limit')
                    total += info.file_size
                    if total > limits.wheel_uncompressed_bytes:
                        _fail('Wheel uncompressed bytes exceed bound', subcheck='zip_uncompressed_size_limit')
                    source_entries.append((safe, directory))
                    destination = _mapped_destination(info.filename, wheel_base, directory)
                    if destination is not None:
                        destination_entries.append((destination, directory))
                    if safe.split('/')[0].endswith('.dist-info') and safe.split('/')[0] != dist_info:
                        _fail('Wheel contains foreign top-level dist-info', subcheck='layout_foreign_dist_info')
                _check_collisions(source_entries)
                _check_collisions(destination_entries)
                files = {i.filename for i in infos if not i.is_dir()}
                if not {record_path, metadata_path, wheel_path} <= files:
                    _fail('Required root METADATA/WHEEL/RECORD is missing', subcheck='layout_required_metadata_missing')
                for info in infos:
                    directory = info.is_dir()
                    destination = _mapped_destination(info.filename, wheel_base, directory)
                    capture = info.filename in {record_path, metadata_path, wheel_path, 'distutils-precedence.pth'}
                    cap = limits.record_bytes if info.filename == record_path else limits.metadata_bytes
                    if capture and info.file_size > cap:
                        _fail('Metadata or startup hook exceeds bounded size', subcheck='metadata_size_limit')
                    h256, h384, h512 = hashlib.sha256(), hashlib.sha384(), hashlib.sha512()
                    chunks = []
                    count = 0
                    with archive.open(info, 'r') as member:
                        while True:
                            chunk = member.read(1024 * 1024)
                            if not chunk:
                                break
                            count += len(chunk)
                            if count > info.file_size or count > limits.member_bytes:
                                _fail('Member expanded beyond its declared size', subcheck='zip_member_expansion_limit')
                            for digest in (h256, h384, h512):
                                digest.update(chunk)
                            if capture:
                                chunks.append(chunk)
                    if count != info.file_size:
                        _fail('ZIP member size mismatch', subcheck='zip_member_size_mismatch')
                    digest_bytes = {'sha256': h256.digest(), 'sha384': h384.digest(), 'sha512': h512.digest()}
                    if not directory:
                        digests[info.filename] = (count, digest_bytes)
                    if capture:
                        metadata_blobs[info.filename] = b''.join(chunks)
                    if destination is not None:
                        inventory.append(VerifiedMember(info.filename, destination, count, h256.hexdigest(), directory,
                                                        destination != info.filename.rstrip('/')))
                        first = destination.split('/')[0].casefold()
                        base = destination.rsplit('/', 1)[-1].casefold()
                        if first in ('sitecustomize', 'usercustomize') or re.match(r'^(sitecustomize|usercustomize)\.', first):
                            _fail('Unknown Python startup customization is forbidden', subcheck='startup_customization_forbidden')
                        if base.endswith(('.pyc', '.pyo')):
                            _fail('Precompiled Python bytecode is outside the reviewed source-only installation policy', subcheck='startup_bytecode_forbidden')
                        if base.endswith('.pth'):
                            if (record['name'], record['version'], destination, info.filename) != (
                                    'setuptools', '84.0.0', 'distutils-precedence.pth', 'distutils-precedence.pth'):
                                _fail('Unknown startup .pth hook is forbidden', subcheck='startup_pth_forbidden')
                            if metadata_blobs[info.filename] != SETUPTOOLS_PTH:
                                _fail('Setuptools startup hook differs from the exact statically audited bytes', subcheck='startup_setuptools_pth_mismatch')
                            hook = destination
                if hook and (digests.get('_distutils_hack/__init__.py', (0, {}))[1].get('sha256', b'').hex() != SETUPTOOLS_SHIM_SHA256):
                    _fail('Setuptools hook target differs from the statically audited shim source', subcheck='startup_setuptools_shim_mismatch')
        except (zipfile.BadZipFile, RuntimeError, OSError, NotImplementedError, EOFError, UnicodeError) as error:
            _fail(f'Invalid or unsupported wheel ZIP: {error}', subcheck='zip_read_failed')
        after = os.fstat(stream.fileno())
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            _fail('Wheel changed during validation', subcheck='archive_changed')
    _validate_record(metadata_blobs[record_path], record_path, digests)
    metadata_data = metadata_blobs[metadata_path]
    metadata_hash = hashlib.sha256(metadata_data).hexdigest()
    expected_metadata_hash = wheel.get('core_metadata_sha256')
    if expected_metadata_hash is not None and metadata_hash != expected_metadata_hash:
        _fail('Embedded METADATA differs from the frozen core metadata SHA256', subcheck='metadata_sha256_pin_mismatch')
    metadata = _parse_headers(metadata_data, 'METADATA')
    if canonicalize_name(_header(metadata, 'Name', True)) != record['name'] or _header(metadata, 'Version', True) != record['version']:
        _fail('Embedded package Name/Version differs from the pin', subcheck='metadata_package_identity_mismatch')
    metadata_version = _header(metadata, 'Metadata-Version', True)
    if metadata_version not in {'1.0', '1.1', '1.2', '2.1', '2.2', '2.3', '2.4'}:
        _fail('Unsupported core metadata version; explicit review required', subcheck='metadata_version_unsupported',
              observed_metadata_version=metadata_version)
    _validate_dynamic_metadata(metadata, metadata_version)
    requires_python = _header(metadata, 'Requires-Python')
    try:
        if SpecifierSet(requires_python or '') != SpecifierSet(record['requires_python'] or ''):
            _fail('Embedded Requires-Python differs from the final manifest', subcheck='metadata_requires_python_mismatch')
        if not SpecifierSet(requires_python or '').contains(environment['python_full_version'], prereleases=True):
            _fail('Embedded Requires-Python excludes the fixed target', subcheck='metadata_requires_python_target_excluded')
    except InvalidSpecifier as error:
        _fail(f'Invalid embedded Requires-Python: {error}', subcheck='metadata_requires_python_invalid')
    requirements = tuple(str(value) for value in metadata.get_all('Requires-Dist', []))
    if len(requirements) > 10000:
        _fail('Too many dependency requirements', subcheck='dependency_count_limit')
    applicable = _applicable(requirements, environment)
    if Counter(map(_requirement_key, applicable)) != Counter(map(_requirement_key, record['requires_dist_applicable'])):
        _fail('Embedded applicable dependencies differ from the fixed runtime dependency graph', subcheck='dependency_graph_mismatch')
    extras = tuple(canonicalize_name(str(value)) for value in metadata.get_all('Provides-Extra', []))
    wheel_metadata = _parse_headers(metadata_blobs[wheel_path], 'WHEEL')
    if _header(wheel_metadata, 'Wheel-Version', True) != '1.0':
        _fail('Unsupported Wheel-Version', subcheck='wheel_version_unsupported')
    if _header(wheel_metadata, 'Root-Is-Purelib', True) not in {'true', 'false'}:
        _fail('Invalid Root-Is-Purelib', subcheck='wheel_root_is_purelib_invalid')
    try:
        embedded_tags = frozenset(tag for value in wheel_metadata.get_all('Tag', []) for tag in parse_tag(str(value)))
    except ValueError as error:
        _fail(f'Invalid embedded wheel tag: {error}', subcheck='wheel_tag_invalid')
    if embedded_tags != filename_tags or not embedded_tags & tags:
        _fail('Embedded wheel tags differ from the filename or runtime', subcheck='wheel_tag_mismatch')
    if hook and metadata_hash != SETUPTOOLS_AUDIT['metadata_sha256']:
        _fail('Setuptools startup-hook metadata differs from its audited identity', subcheck='startup_setuptools_metadata_mismatch')
    license_files = tuple(str(value) for value in metadata.get_all('License-File', []))
    # Follow the reviewed v3 actual-member strategy: a declared relative path can
    # be packaged at archive root, under dist-info/licenses, or another supplied
    # prefix. Never guess a missing file or impose a new notice filename gate.
    # All matches must already be ordinary retained, RECORD-hash-verified files.
    retained_files = {member.archive_path for member in inventory if not member.directory}
    unrecorded = {record_path, record_path + '.jws', record_path + '.p7s'}
    for declared in license_files:
        _safe_path(declared)
        matches = {name for name in retained_files - unrecorded
                   if name == declared or name.endswith('/' + declared)}
        if not matches:
            _fail('Declared License-File has no retained RECORD-verified member', subcheck='license_declared_member_missing')
    return VerifiedWheel(record['name'], record['version'], path.name, str(path.absolute()), actual_hash,
                         initial.st_size, total, metadata_hash, requirements, applicable, extras,
                         tuple(inventory), license_files, _header(metadata, 'License-Expression'),
                         _header(metadata, 'License'), hook)


def _validate_record(data: bytes, record_path: str, digests: dict) -> None:
    try:
        text = data.decode('utf-8', errors='strict')
        rows = list(csv.reader(io.StringIO(text, newline=''), strict=True))
    except (UnicodeError, csv.Error) as error:
        _fail(f'Invalid RECORD: {error}', subcheck='record_parse_invalid')
    if len(rows) > len(digests) or any(len(row) != 3 for row in rows):
        _fail('RECORD row count or shape mismatch', subcheck='record_row_shape_invalid')
    listed = set()
    signature_exemptions = {record_path + '.jws', record_path + '.p7s'}
    for name, digest_field, size_field in rows:
        _safe_path(name)
        if name in listed or name not in digests:
            _fail('RECORD contains duplicate or nonexistent member', subcheck='record_member_invalid')
        listed.add(name)
        if name == record_path:
            if digest_field or size_field:
                _fail('RECORD self-row must have empty hash and size', subcheck='record_self_row_invalid')
            continue
        if not digest_field or not size_field:
            _fail('Every ordinary wheel file requires a RECORD digest and size', subcheck='record_digest_or_size_missing')
        if not re.fullmatch(r'0|[1-9][0-9]*', size_field) or int(size_field) != digests[name][0]:
            _fail('RECORD byte size mismatch', subcheck='record_size_mismatch')
        algorithm, sep, encoded = digest_field.partition('=')
        if sep != '=' or algorithm not in {'sha256', 'sha384', 'sha512'} or not re.fullmatch(r'[A-Za-z0-9_-]+', encoded):
            _fail('RECORD digest must be canonical SHA256/SHA384/SHA512 URL-safe base64', subcheck='record_digest_format_invalid')
        expected = base64.urlsafe_b64encode(digests[name][1][algorithm]).rstrip(b'=').decode('ascii')
        if encoded != expected:
            _fail('RECORD digest mismatch', subcheck='record_digest_mismatch')
    if record_path not in listed or (set(digests) - listed) - signature_exemptions:
        _fail('RECORD does not cover every wheel file', subcheck='record_coverage_incomplete')


def _check_dependency_closure(wheels: tuple[VerifiedWheel, ...], environment: dict) -> tuple[tuple[str, str, str], ...]:
    by_name = {wheel.name: wheel for wheel in wheels}
    if len(by_name) != len(wheels):
        _fail('Duplicate verified package in closure', subcheck='closure_duplicate_package')
    requested_extras = {name: set() for name in by_name}
    edges = set()
    changed = True
    while changed:
        changed = False
        for wheel in wheels:
            active = _applicable(wheel.requirements, environment, ('', *sorted(requested_extras[wheel.name])))
            for raw in active:
                requirement = _requirement(raw)
                target_name = canonicalize_name(requirement.name)
                target = by_name.get(target_name)
                if target is None:
                    _fail(f'Runtime dependency outside the fixed wheel closure: {wheel.name} -> {target_name}', subcheck='closure_dependency_missing')
                if not requirement.specifier.contains(target.version, prereleases=True):
                    _fail(f'Pinned version violates dependency constraint: {wheel.name} -> {target_name}', subcheck='closure_dependency_version_mismatch')
                for extra in requirement.extras:
                    extra = canonicalize_name(extra)
                    if extra not in target.provides_extras:
                        _fail(f'Dependency requests undeclared extra: {target_name}[{extra}]', subcheck='closure_dependency_extra_undeclared')
                    if extra not in requested_extras[target_name]:
                        requested_extras[target_name].add(extra)
                        changed = True
                edges.add((wheel.name, target_name, raw))
    # Extra-enabled requirements cannot silently expand the approved metadata graph.
    for wheel in wheels:
        active = _applicable(wheel.requirements, environment, ('', *sorted(requested_extras[wheel.name])))
        if Counter(map(_requirement_key, active)) != Counter(map(_requirement_key, wheel.applicable_requirements)):
            _fail(f'Dependency extras expand the reviewed graph for {wheel.name}', subcheck='closure_dependency_extras_expansion')
    return tuple(sorted(edges))


def validate_wheelhouse(wheel_paths, manifest: dict, marker_environment: dict[str, str], supported_tags,
                        *, limits: Limits = DEFAULT_LIMITS) -> ValidationReport:
    """Validate all exact pins and every archive before installation/execution.

    The caller must keep validated inputs immutable, preserve every inventory
    member, honor destination mappings, and use a safe installer with no overwrite
    or symlink traversal. This validator performs no filesystem writes.
    """
    if packaging.__version__ != PACKAGING_VERSION:
        _fail('The audited packaging 26.3 parser is required; no parser fallback', subcheck='parser_version_mismatch')
    records = validate_manifest(manifest)
    environment, tags = validate_runtime(marker_environment, supported_tags)
    if isinstance(wheel_paths, (str, bytes, Path)):
        _fail('Supply the explicit 49 wheel paths', subcheck='wheelhouse_path_shape_invalid')
    paths = tuple(Path(p) for p in wheel_paths)
    expected_files = {r['wheel']['filename']: r for r in records.values()}
    if len(paths) != 49 or len({p.name for p in paths}) != 49 or {p.name for p in paths} != set(expected_files):
        _fail('Wheelhouse must be exactly the finalized 49 wheels, without extras or substitutions', subcheck='wheelhouse_inventory_mismatch')
    if sum(r['wheel']['bytes'] for r in records.values()) > limits.total_archive_bytes:
        _fail('Total archive byte limit exceeded', subcheck='wheelhouse_archive_size_limit')
    verified = []
    uncompressed = 0
    destination_owners = {}
    for path in sorted(paths, key=lambda p: p.name):
        remaining = limits.total_uncompressed_bytes - uncompressed
        if remaining <= 0:
            _fail('Total uncompressed closure exceeds bound', subcheck='wheelhouse_uncompressed_size_limit')
        wheel_limits = replace(limits, wheel_uncompressed_bytes=min(limits.wheel_uncompressed_bytes, remaining))
        wheel = _validate_wheel(path, expected_files[path.name], environment, tags, wheel_limits)
        uncompressed += wheel.uncompressed_bytes
        if uncompressed > limits.total_uncompressed_bytes:
            _fail('Total uncompressed closure exceeds bound', subcheck='wheelhouse_uncompressed_size_limit')
        for member in wheel.members:
            destination = member.destination.casefold()
            if not member.directory:
                if destination in destination_owners:
                    _fail(f'Cross-wheel installation collision at {member.destination}', subcheck='wheelhouse_destination_collision')
                destination_owners[destination] = wheel.name
        verified.append(wheel)
    all_entries = []
    seen_directories = set()
    for wheel in verified:
        for member in wheel.members:
            if member.directory:
                key = member.destination.casefold()
                if key in seen_directories:
                    continue
                seen_directories.add(key)
            all_entries.append((member.destination, member.directory))
    _check_collisions(all_entries)
    wheels = tuple(verified)
    edges = _check_dependency_closure(wheels, environment)
    return ValidationReport(wheels, edges, sum(w.size for w in wheels), uncompressed, packaging.__version__)
