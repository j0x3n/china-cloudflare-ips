# china-cloudflare-ips

This repository provides automatically updated IP lists for a specific routing issue:

- For tools that only support the `Bypass China IP` rule mode, such as `SSR Plus+`
- Some overseas sites are routed directly by mistake
- Those sites may actually sit behind Cloudflare or other shared CDN / edge networks
- The site or upstream protection may detect a China egress IP and block access

This repository merges China IP ranges with common shared CDN and edge network ranges as a supplemental data source for that scenario.

## Fixed URLs

- `https://raw.githubusercontent.com/j0x3n/china-cloudflare-ips/main/all.txt`
- `https://raw.githubusercontent.com/j0x3n/china-cloudflare-ips/main/ipv4.txt`
- `https://raw.githubusercontent.com/j0x3n/china-cloudflare-ips/main/ipv6.txt`

## Included Sources

- China IPv4 / IPv6
- Cloudflare
- Amazon CloudFront
- Fastly
- Azure Front Door Frontend

## Upstream Data

- China IPv4: `https://ispip.clang.cn/all_cn.txt`
- China IPv6: `https://ispip.clang.cn/all_cn_ipv6.txt`
- Cloudflare IPv4: `https://www.cloudflare.com/ips-v4`
- Cloudflare IPv6: `https://www.cloudflare.com/ips-v6`
- Amazon AWS IP ranges: `https://ip-ranges.amazonaws.com/ip-ranges.json`
- Fastly Public IP List: `https://api.fastly.com/public-ip-list`
- Azure Service Tags Public JSON: `AzureFrontDoor.Frontend`

## Auto Update

GitHub Actions updates the lists every day at `02:00` Beijing time.

## Local Run

```bash
python scripts/update_lists.py
```
