from __future__ import annotations

import argparse
from pathlib import Path

RICH_URL = "https://files.pythonhosted.org/packages/14/25/b208c5683343959b670dc001595f2f3737e051da617f66c31f7c4fa93abc/rich-14.3.3-py3-none-any.whl"
RICH_SHA = "793431c1f8619afa7d3b52b2cdec859562b950ea0d4b6b505397612db8d5362d"
MARKDOWN_URL = "https://files.pythonhosted.org/packages/94/54/e7d793b573f298e1c9013b8c4dade17d481164aa517d1d7148619c2cedbf/markdown_it_py-4.0.0-py3-none-any.whl"
MARKDOWN_SHA = "87327c59b172c5011896038353a81343b6754500a08cd7a4973bb48c6d578147"
MDURL_URL = "https://files.pythonhosted.org/packages/b3/38/89ba8ad64ae25be8de66a6d463314cf1eb366222074cfda9ee839c56a4b4/mdurl-0.1.2-py3-none-any.whl"
MDURL_SHA = "84008a41e51615a49fc9966191ff91509e3c40b939176e643fd50a5c2196b8f8"
PYGMENTS_URL = "https://files.pythonhosted.org/packages/c7/21/705964c7812476f378728bdf590ca4b771ec72385c533964653c68e86bdc/pygments-2.19.2-py3-none-any.whl"
PYGMENTS_SHA = "86540386c03d588bb81d44bc3928634ff26449851e99741617ecb9037ee5ec0b"


def build_formula(tag: str, sha256: str) -> str:
    return f"""class GirlfriendInCli < Formula
  include Language::Python::Virtualenv

  desc "Terminal-native romance simulator for vibe coders"
  homepage "https://github.com/NomaDamas/girlfriend-in-cli"
  url "https://github.com/NomaDamas/girlfriend-in-cli/archive/refs/tags/{tag}.tar.gz"
  sha256 "{sha256}"
  license "Elastic-2.0"

  depends_on "python@3.12"

  resource "rich" do
    url "{RICH_URL}"
    sha256 "{RICH_SHA}"
  end

  resource "markdown-it-py" do
    url "{MARKDOWN_URL}"
    sha256 "{MARKDOWN_SHA}"
  end

  resource "mdurl" do
    url "{MDURL_URL}"
    sha256 "{MDURL_SHA}"
  end

  resource "pygments" do
    url "{PYGMENTS_URL}"
    sha256 "{PYGMENTS_SHA}"
  end

  def install
    virtualenv_install_with_resources
    bin.env_script_all_files(
      libexec/"bin",
      GIRLFRIEND_GENERATOR_INSTALL_METHOD: "brew",
      GIRLFRIEND_GENERATOR_PACKAGE_NAME: "girlfriend-in-cli"
    )
  end

  test do
    assert_match "romance simulation", shell_output("#{{bin}}/mygf --help")
  end
end
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_formula(args.tag, args.sha256), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
