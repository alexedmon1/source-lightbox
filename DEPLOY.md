# Hosting galleries on a LAN workstation (nginx or Apache)

A built gallery is **fully static** — the manifest is inlined into `index.html`
(`window.MANIFEST = …`), every asset reference is relative, and there is no
server-side code. So the host needs **only a static web server** — no Python, no
`uv`, no source-lightbox/source-analytics. Because all paths are relative,
galleries host cleanly under a sub-path (`/ms1/`, `/ms2/`).

Either **nginx** (§2a) or **Apache 2.4** (§2b) works — both ship a ready config
in `deploy/`. The web server is the only thing that differs; the read-only drive
mount (§1) and rebuild flow (§3) are identical, since both servers run as the
same `www-data` user on Debian/Ubuntu.

**Build vs serve are separate.** Keep *building* galleries on the machine that
has `source-analytics` + the Allen atlas (brain mosaics need them). The
workstation only *serves* the finished `gallery*/` directories.

Worked example: an Ubuntu workstation serving MS1 (`gallery/`) and MS2
(`gallery_treatment/`) from a mounted FORGE drive, LAN-only.

## 1. Mount the drive (read-only) so the web server can read it

The FORGE drive is NTFS. Find its UUID, then add an `/etc/fstab` line so it
mounts at boot, owned by the web server's `www-data` user (same user for nginx
and Apache):

```bash
sudo blkid            # note the UUID of the FORGE partition
sudo mkdir -p /mnt/forge
```

```fstab
# /etc/fstab  (ntfs3 kernel driver; use ntfs-3g if ntfs3 is unavailable)
UUID=XXXX-XXXX  /mnt/forge  ntfs3  ro,uid=www-data,gid=www-data,umask=0027,nofail,x-systemd.automount  0  0
```

```bash
sudo systemctl daemon-reload && sudo mount -a
ls /mnt/forge/FORGE/gallery_treatment/index.html   # sanity check
```

- `ro` — serve-only; the host never writes to the drive.
- `uid/gid=www-data` — the web server can read every file.
- `nofail,x-systemd.automount` — boot doesn't hang if the drive is absent.

> If the drive is **network-shared** (e.g. SMB from the build machine) rather
> than physically moved, mount that share instead — the rest is identical. If
> physically moved, build the gallery *before* moving the drive.

## 2a. Install nginx + the site

```bash
sudo apt update && sudo apt install -y nginx
sudo mkdir -p /srv/forge-galleries
sudo cp deploy/landing.html /srv/forge-galleries/index.html
sudo cp deploy/nginx-galleries.conf /etc/nginx/sites-available/forge-galleries
sudo ln -sf /etc/nginx/sites-available/forge-galleries /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
# edit the alias paths in the conf to match your mount, then:
sudo nginx -t && sudo systemctl reload nginx
```

Browse from any LAN machine to **`http://<workstation-ip>/`** → landing page →
`/ms1/` and `/ms2/`.

## 2b. Install Apache 2.4 + the site (alternative to 2a)

```bash
sudo apt update && sudo apt install -y apache2
sudo mkdir -p /srv/forge-galleries
sudo cp deploy/landing.html /srv/forge-galleries/index.html
sudo cp deploy/apache-galleries.conf /etc/apache2/sites-available/forge-galleries.conf
sudo a2ensite forge-galleries
sudo a2dissite 000-default          # drop the stock default site
# edit the Alias paths in the conf to match your mount, then:
sudo apache2ctl configtest && sudo systemctl reload apache2
```

`mod_alias` and `mod_dir` are enabled by default, so the sub-path serving and the
`/ms2` → `/ms2/` trailing-slash redirect work with no extra modules. Browse to
**`http://<workstation-ip>/`** → landing page → `/ms1/` and `/ms2/`.

## 3. Updating after a rebuild

Rebuild on the source machine (`bash scripts/build_gallery.sh study_treatment.yaml`).
The files on the shared drive update and the web server serves them immediately —
the build stamps a fresh `?v=` on `index.html`'s assets, so browsers pick up
changes on refresh. No reload needed. (If the drive was physically moved, re-copy
or re-mount the updated drive.)

## Options / troubleshooting

- **LAN password:** uncomment the auth block in the conf, then
  `sudo htpasswd -c /etc/nginx/.htpasswd labuser` (nginx) or
  `sudo htpasswd -c /etc/apache2/.htpasswd labuser` (Apache).
- **Adding a gallery:** nginx — copy a `location /msN/ { alias …; }` block;
  Apache — copy an `Alias /msN …` + matching `<Directory>` block. Then add a card
  to `landing.html`.
- **403 Forbidden:** the web server (`www-data`) can't read the path — re-check
  the mount `uid/gid/umask`, and that every parent dir is executable (`x`) for it.
  On Apache, also confirm the gallery dir has a `<Directory>` block with
  `Require all granted`.
- **AppArmor:** if serving from `/mnt` is blocked, allow the web server read
  access to the mount path (`/etc/apparmor.d/` profile — `usr.sbin.nginx` or
  `usr.sbin.apache2`) or mount under `/srv`.
- **Firewall:** `sudo ufw allow 80/tcp` if `ufw` is enabled.
- **Internet-facing instead of LAN:** add HTTPS — easiest is Caddy
  (automatic certs), or nginx/Apache + certbot — and require auth.
