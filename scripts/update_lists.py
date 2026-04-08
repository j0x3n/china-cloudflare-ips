#!/usr/bin/env python3
from __future__ import annotations

import ipaddress
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT_DIR = Path(__file__).resolve().parent.parent

USER_AGENT = "Mozilla/5.0 (compatible; china-cloudflare-ips/1.0; +https://github.com/j0x3n/china-cloudflare-ips)"
AZURE_SERVICE_TAGS_URL = (
    "https://download.microsoft.com/download/7/1/D/71D86715-5596-4529-9B13-DA13A5DE5B63/"
    "ServiceTags_Public_{date}.json"
)

IPv4Net = ipaddress.IPv4Network
IPv6Net = ipaddress.IPv6Network
Network = IPv4Net | IPv6Net


@dataclass(frozen=True)
class Dataset:
    name: str
    sources: tuple[str, ...]
    ipv4: tuple[IPv4Net, ...]
    ipv6: tuple[IPv6Net, ...]


def fetch_text(url: str, retries: int = 3, timeout: int = 30) -> str:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            request = Request(url, headers={"User-Agent": USER_AGENT})
            with urlopen(request, timeout=timeout) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset)
        except (HTTPError, URLError, TimeoutError) as exc:
            last_error = exc
            if attempt == retries:
                break
            time.sleep(attempt)
    raise RuntimeError(f"failed to fetch {url}: {last_error}") from last_error


def fetch_json(url: str, retries: int = 3, timeout: int = 30) -> dict:
    return json.loads(fetch_text(url, retries=retries, timeout=timeout))


def parse_cidr_lines(text: str) -> list[Network]:
    networks: list[Network] = []
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        networks.append(ipaddress.ip_network(line, strict=False))
    return networks


def split_networks(networks: list[Network]) -> tuple[list[IPv4Net], list[IPv6Net]]:
    ipv4: list[IPv4Net] = []
    ipv6: list[IPv6Net] = []
    for network in networks:
        if isinstance(network, IPv4Net):
            ipv4.append(network)
        else:
            ipv6.append(network)
    return ipv4, ipv6


def sort_unique_ipv4(networks: list[IPv4Net]) -> list[IPv4Net]:
    return sorted(set(networks), key=lambda network: (int(network.network_address), network.prefixlen))


def sort_unique_ipv6(networks: list[IPv6Net]) -> list[IPv6Net]:
    return sorted(set(networks), key=lambda network: (int(network.network_address), network.prefixlen))


def write_list_file(path: Path, networks: list[Network]) -> None:
    content = "\n".join(str(network) for network in networks)
    if content:
        content += "\n"
    path.write_text(content, encoding="utf-8")


def fetch_cloudflare() -> Dataset:
    ipv4_url = "https://www.cloudflare.com/ips-v4"
    ipv6_url = "https://www.cloudflare.com/ips-v6"
    ipv4 = sort_unique_ipv4(split_networks(parse_cidr_lines(fetch_text(ipv4_url)))[0])
    ipv6 = sort_unique_ipv6(split_networks(parse_cidr_lines(fetch_text(ipv6_url)))[1])
    return Dataset("cloudflare", (ipv4_url, ipv6_url), tuple(ipv4), tuple(ipv6))


def fetch_china() -> Dataset:
    ipv4_url = "https://ispip.clang.cn/all_cn.txt"
    ipv6_url = "https://ispip.clang.cn/all_cn_ipv6.txt"
    ipv4 = sort_unique_ipv4(split_networks(parse_cidr_lines(fetch_text(ipv4_url)))[0])
    ipv6 = sort_unique_ipv6(split_networks(parse_cidr_lines(fetch_text(ipv6_url)))[1])
    return Dataset("china", (ipv4_url, ipv6_url), tuple(ipv4), tuple(ipv6))


def fetch_fastly() -> Dataset:
    url = "https://api.fastly.com/public-ip-list"
    payload = fetch_json(url)
    ipv4 = sort_unique_ipv4([ipaddress.ip_network(item, strict=False) for item in payload["addresses"]])
    ipv6 = sort_unique_ipv6([ipaddress.ip_network(item, strict=False) for item in payload["ipv6_addresses"]])
    return Dataset("fastly", (url,), tuple(ipv4), tuple(ipv6))


def fetch_cloudfront() -> Dataset:
    url = "https://ip-ranges.amazonaws.com/ip-ranges.json"
    payload = fetch_json(url)
    ipv4 = sort_unique_ipv4(
        [
            ipaddress.ip_network(item["ip_prefix"], strict=False)
            for item in payload["prefixes"]
            if item.get("service") == "CLOUDFRONT" and item.get("region") == "GLOBAL"
        ]
    )
    ipv6 = sort_unique_ipv6(
        [
            ipaddress.ip_network(item["ipv6_prefix"], strict=False)
            for item in payload["ipv6_prefixes"]
            if item.get("service") == "CLOUDFRONT" and item.get("region") == "GLOBAL"
        ]
    )
    return Dataset("cloudfront", (url,), tuple(ipv4), tuple(ipv6))


def fetch_azure_frontdoor() -> Dataset:
    payload: dict | None = None
    source_url: str | None = None
    today = datetime.now(timezone.utc).date()

    for offset in range(0, 21):
        date_text = (today - timedelta(days=offset)).strftime("%Y%m%d")
        candidate_url = AZURE_SERVICE_TAGS_URL.format(date=date_text)
        try:
            payload = fetch_json(candidate_url)
            source_url = candidate_url
            break
        except RuntimeError:
            continue

    if payload is None or source_url is None:
        raise RuntimeError("failed to find a recent Azure Service Tags public JSON document")

    prefixes: list[Network] = []
    for item in payload.get("values", []):
        if item.get("name") != "AzureFrontDoor.Frontend":
            continue
        for prefix in item.get("properties", {}).get("addressPrefixes", []):
            prefixes.append(ipaddress.ip_network(prefix, strict=False))
        break
    else:
        raise RuntimeError("AzureFrontDoor.Frontend not found in Azure Service Tags JSON")

    ipv4, ipv6 = split_networks(prefixes)
    return Dataset(
        "azure_front_door_frontend",
        (source_url,),
        tuple(sort_unique_ipv4(ipv4)),
        tuple(sort_unique_ipv6(ipv6)),
    )


def build_datasets() -> list[Dataset]:
    return [
        fetch_china(),
        fetch_cloudflare(),
        fetch_cloudfront(),
        fetch_fastly(),
        fetch_azure_frontdoor(),
    ]


def write_outputs(datasets: list[Dataset]) -> None:
    merged_ipv4 = sort_unique_ipv4([network for dataset in datasets for network in dataset.ipv4])
    merged_ipv6 = sort_unique_ipv6([network for dataset in datasets for network in dataset.ipv6])
    merged_all: list[Network] = [*merged_ipv4, *merged_ipv6]

    write_list_file(ROOT_DIR / "ipv4.txt", merged_ipv4)
    write_list_file(ROOT_DIR / "ipv6.txt", merged_ipv6)
    write_list_file(ROOT_DIR / "all.txt", merged_all)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "datasets": {
            dataset.name: {
                "sources": list(dataset.sources),
                "ipv4": len(dataset.ipv4),
                "ipv6": len(dataset.ipv6),
            }
            for dataset in datasets
        },
        "totals": {
            "ipv4": len(merged_ipv4),
            "ipv6": len(merged_ipv6),
            "all": len(merged_all),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def main() -> int:
    try:
        write_outputs(build_datasets())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
