"""Read an upstream mu300 kernel tarball without extracting files to disk."""
import argparse
import gzip
import hashlib
import tarfile


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    args = parser.parse_args()
    try:
        with tarfile.open(args.archive, "r:gz") as archive:
            image = archive.extractfile("./Image")
            if image is None:
                raise ValueError("Image is missing")
            data = image.read()
        start = data.index(b"IKCFG_ST") + len(b"IKCFG_ST")
        config = gzip.decompress(data[start:data.index(b"IKCFG_ED", start)])
    except (OSError, EOFError, KeyError, ValueError, tarfile.TarError) as error:
        parser.exit(1, f"Cannot read embedded config: {error}\n")

    settings = sorted(line for line in config.splitlines()
                      if line.startswith((b"CONFIG_", b"# CONFIG_")))
    if not settings:
        parser.exit(1, "Embedded config contains no Kconfig settings\n")
    print("config.raw.sha256=" + sha256(config))
    print("config.sorted.sha256=" + sha256(b"\n".join(settings) + b"\n"))


if __name__ == "__main__":
    main()
