# Hosting galleries on a LAN workstation (nginx)

A built gallery is **fully static** — the manifest is inlined into `index.html`
(`window.MANIFEST = …`), every asset reference is relative, and there is no
server-side code. So the host needs **only a static web server** (nginx) — no
Python, no `uv`, no source-lightbox/source-analytics. Because all paths are
relative, galleries host cleanly under a sub-path (`/ms1/`, `/ms2/`).

**Build vs serve are separate.** Keep *building* galleries on the machine that
has `source-analytics` + the Allen atlas (brain mosaics need them). The
workstation only *serves* the finished `gallery*/` directories.

Worked example: an Ubuntu workstation serving MS1 (`gallery/`) and MS2
(`gallery_treatment/`) from a mounted FORGE drive, LAN-only.

## 1. Mount the drive (read-only) so nginx can read it

The FORGE drive is NTFS. Find its UUID, then add an `/etc/fstab` line so it
mounts at boot, owned by nginx's `www-data` user:

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
- `uid/gid=www-data` — nginx can read every file.
- `nofail,x-systemd.automount` — boot doesn't hang if the drive is absent.

> If the drive is **network-shared** (e.g. SMB from the build machine) rather
> than physically moved, mount that share instead — the rest is identical. If
> physically moved, build the gallery *before* moving the drive.

## 2. Install nginx + the site

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

## 3. Updating after a rebuild

Rebuild on the source machine (`bash scripts/build_gallery.sh study_treatment.yaml`).
The files on the shared drive update and nginx serves them immediately — the
build stamps a fresh `?v=` on `index.html`'s assets, so browsers pick up changes
on refresh. No nginx reload needed. (If the drive was physically moved, re-copy
or re-mount the updated drive.)

## Options / troubleshooting

- **LAN password:** uncomment the `auth_basic` lines in the conf and
  `sudo htpasswd -c /etc/nginx/.htpasswd labuser`.
- **Adding a gallery:** copy a `location /msN/ { alias …; }` block and add a card
  to `landing.html`.
- **403 Forbidden:** nginx (`www-data`) can't read the path — re-check the mount
  `uid/gid/umask`, and that every parent dir is executable (`x`) for it.
- **AppArmor:** if serving from `/mnt` is blocked, allow nginx read access to the
  mount path (`/etc/apparmor.d/` profile) or mount under `/srv`.
- **Firewall:** `sudo ufw allow 80/tcp` if `ufw` is enabled.
- **Internet-facing instead of LAN:** add HTTPS — easiest is Caddy
  (automatic certs) or nginx + certbot — and require auth.
