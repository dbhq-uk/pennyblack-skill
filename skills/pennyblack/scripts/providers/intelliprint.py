"""Intelliprint provider.

Every Intelliprint-specific fact in pennyblack lives in this file. If you are
adding a second provider, this is the only file you need to read as a model.

Notes taken from the published OpenAPI 3.1.1 spec at
https://www.intelliprint.net/openapi.json:

- Costs come back as integers that must be divided by 10^8 to get currency
  units. Not 100. Getting this wrong understates a letter by a factor of a
  million, so it is done in exactly one place: _money().
- A print job is created unconfirmed by default. Unconfirmed jobs are not
  charged and not printed. `POST /prints/{id}` with confirmed=true commits it.
  That two-step is what pennyblack's whole safety story rests on.
- The response carries `letters[].pdf`, a signed URL to a preview of the real
  letter, valid for one hour. It is the best thing in this API.
- The API accepts application/x-www-form-urlencoded with PHP-style bracket
  keys, per the vendor's own cURL sample. Multipart is only needed when
  uploading a file.
"""

import json
import mimetypes
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from .base import Address, Cancellation, Cost, Draft, Mailing, Provider

API_BASE = "https://api.intelliprint.net/v1"

#: Intelliprint returns money as an integer scaled by 10^8.
COST_DIVISOR = 100_000_000


class IntelliprintError(Exception):
    def __init__(self, message, status=None, body=None):
        super().__init__(message)
        self.status = status
        self.body = body


def _money(obj: dict) -> Cost:
    """Turn Intelliprint's scaled integers into whole pence.

    amount / 10^8 gives pounds; multiplying by 100 gives pence. Done in one
    step to avoid a float round-trip: (amount * 100) // 10^8.
    """
    if not obj:
        return Cost(0, 0, 0, "GBP")

    def pence(key):
        raw = obj.get(key) or 0
        return round(raw * 100 / COST_DIVISOR)

    return Cost(
        amount_pence=pence("amount"),
        tax_pence=pence("tax"),
        total_pence=pence("after_tax"),
        currency=obj.get("currency", "GBP"),
    )


def _testmode(payload: dict):
    """The job's test flag, or None if the payload does not carry one."""
    return bool(payload["testmode"]) if "testmode" in payload else None


def _flatten(data, parent="", out=None):
    """Encode nested dicts and lists as PHP-style bracket keys.

    {"recipients": [{"address": {"name": "A"}}]}
      -> recipients[0][address][name]=A

    This is the shape the vendor's own cURL example uses.
    """
    out = {} if out is None else out
    if isinstance(data, dict):
        for k, v in data.items():
            key = f"{parent}[{k}]" if parent else str(k)
            _flatten(v, key, out)
    elif isinstance(data, (list, tuple)):
        for i, v in enumerate(data):
            _flatten(v, f"{parent}[{i}]", out)
    elif isinstance(data, bool):
        out[parent] = "true" if data else "false"
    elif data is None:
        pass
    else:
        out[parent] = str(data)
    return out


def _multipart(fields: dict, file_field: str, file_path: Path):
    """Build a multipart/form-data body. Only used when sending a PDF."""
    boundary = f"----pennyblack{uuid.uuid4().hex}"
    crlf = b"\r\n"
    parts = []
    for key, value in fields.items():
        parts += [
            f"--{boundary}".encode(),
            f'Content-Disposition: form-data; name="{key}"'.encode(),
            b"",
            str(value).encode("utf-8"),
        ]
    ctype = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    parts += [
        f"--{boundary}".encode(),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{file_path.name}"'.encode(),
        f"Content-Type: {ctype}".encode(),
        b"",
        file_path.read_bytes(),
        f"--{boundary}--".encode(),
        b"",
    ]
    return crlf.join(parts), f"multipart/form-data; boundary={boundary}"


class Intelliprint(Provider):
    name = "intelliprint"

    service_map = {
        "second": "uk_second_class",
        "first": "uk_first_class",
        "signed-second": "uk_second_class_signed_for",
        "signed": "uk_first_class_signed_for",
        "tracked-24": "tracked_24",
        "tracked-48": "tracked_48",
        "special": "uk_special_delivery",
        "special-9am": "uk_special_delivery_9am",
    }

    #: Sheets each envelope holds, from
    #: https://www.intelliprint.net/docs/envelope-and-postcard-sizes. A letter
    #: that needs more is moved to a bigger envelope, and charged for it.
    envelope_capacity = {"c5": 15, "c4": 50, "c4_plus": 250, "a4_box": 1800}
    #: Tracked 24 and 48 cannot use C5, per the same page.
    envelope_excludes = {"tracked-24": {"c5"}, "tracked-48": {"c5"}}

    def __init__(self, config: dict):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.base = config.get("api_base", API_BASE).rstrip("/")
        # Bearer is correct - confirmed against the live API on 2026-09-17, and
        # it is what the OpenAPI security scheme declares. The vendor's own cURL
        # sample sends the bare key instead, so the fallback below stays as a
        # cheap hedge in case they change their minds.
        self._auth_style = config.get("auth_style", "bearer")

    # -- transport ---------------------------------------------------------

    def _auth_header(self, style):
        return f"Bearer {self.api_key}" if style == "bearer" else self.api_key

    def _request(self, method, path, *, fields=None, file_path=None, query=None):
        url = f"{self.base}{path}"
        if query:
            url += "?" + urllib.parse.urlencode(
                {k: v for k, v in query.items() if v is not None}
            )

        body, content_type = None, None
        if fields is not None:
            flat = _flatten(fields)
            if file_path is not None:
                body, content_type = _multipart(flat, "file", Path(file_path))
            else:
                body = urllib.parse.urlencode(flat).encode()
                content_type = "application/x-www-form-urlencoded"

        styles = [self._auth_style]
        if self._auth_style == "bearer":
            styles.append("raw")

        last = None
        for style in styles:
            req = urllib.request.Request(url, data=body, method=method)
            req.add_header("Authorization", self._auth_header(style))
            req.add_header("Accept", "application/json")
            req.add_header("User-Agent", "pennyblack (+https://github.com/dbhq-uk/pennyblack-skill)")
            if content_type:
                req.add_header("Content-Type", content_type)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    self._auth_style = style
                    raw = resp.read().decode("utf-8")
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")
                if exc.code == 401 and style != styles[-1]:
                    last = exc
                    continue
                raise IntelliprintError(
                    self._explain(exc.code, detail), status=exc.code, body=detail
                ) from exc
            except urllib.error.URLError as exc:
                raise IntelliprintError(
                    f"Could not reach Intelliprint at {self.base}: {exc.reason}"
                ) from exc
        raise IntelliprintError("Authentication failed with both header styles", status=401) from last

    @staticmethod
    def _explain(code, detail):
        """Turn an HTTP code into something a person can act on."""
        hints = {
            400: "Intelliprint rejected the request. Check the address and postcode.",
            401: "Intelliprint rejected the API key. Check it at "
                 "https://account.intelliprint.net/api_keys and run setup again.",
            402: "Intelliprint says the account cannot be charged. Check billing.",
            403: "The API key is valid but not permitted to do this.",
            404: "No such print job.",
            413: "The file is too large for Intelliprint to accept.",
            422: "Intelliprint could not process the letter. Often a bad address "
                 "or an unreadable PDF.",
            429: "Rate limited by Intelliprint. Wait and try again.",
        }
        head = hints.get(code, f"Intelliprint returned HTTP {code}.")
        try:
            parsed = json.loads(detail)
            msg = parsed.get("message") or parsed.get("error") or ""
            if isinstance(msg, dict):
                msg = json.dumps(msg)
            if msg:
                return f"{head}\n  Intelliprint said: {msg}"
        except (json.JSONDecodeError, AttributeError):
            pass
        return f"{head}\n  {detail[:400]}" if detail else head

    # -- mapping -----------------------------------------------------------

    def _to_draft(self, payload: dict, service: str) -> Draft:
        letters = payload.get("letters") or []
        preview = next((l.get("pdf") for l in letters if l.get("pdf")), None)
        per_letter = [l.get("sheets") or 0 for l in letters]
        if not any(per_letter) and letters:
            per_letter = [-(-(payload.get("sheets") or 0) // len(letters))]
        return Draft(
            id=payload.get("id", ""),
            provider=self.name,
            cost=_money(payload.get("cost")),
            pages=payload.get("pages", 0),
            sheets=payload.get("sheets", 0),
            service=service,
            testmode=bool(payload.get("testmode")),
            confirmed=bool(payload.get("confirmed")),
            recipients=[
                (l.get("address") or {}).get("name", "") for l in letters
            ],
            preview_url=preview,
            raw=payload,
            addresses=[
                Address(name=a.get("name") or "", line=a.get("line") or "",
                        postcode=a.get("postcode") or "", country=a.get("country") or "GB")
                for a in (l.get("address") or {} for l in letters) if a
            ],
            sheets_per_letter=max(per_letter, default=0),
        )

    def _reverse_service(self, api_value: str) -> str:
        for ours, theirs in self.service_map.items():
            if theirs == api_value:
                return ours
        return api_value

    # -- operations --------------------------------------------------------

    def draft(self, *, source, recipients, service, reference=None,
              testmode=True, **options) -> Draft:
        """Create an unconfirmed print job. Nothing is printed or charged."""
        if not self.supports(service):
            raise IntelliprintError(
                f"Intelliprint does not offer '{service}'. Available: "
                + ", ".join(sorted(self.service_map))
            )
        from_pdf = bool(options.get("address_from_pdf"))
        if from_pdf and recipients:
            raise IntelliprintError(
                "Give recipients or read the address from the PDF, not both.")
        if not recipients and not from_pdf:
            raise IntelliprintError("No recipients given.")

        fields = {
            "type": "letter",
            "testmode": testmode,
            "confirmed": False,
            "postage": {
                "service": self.service_map[service],
                "ideal_envelope": self.envelope_for(service, options.get("envelope")),
            },
            "printing": {
                "double_sided": "yes" if options.get("double_sided", True) else "no",
                "black_and_white": bool(options.get("black_and_white", False)),
            },
        }
        # With no recipients, Intelliprint reads the address from where the
        # envelope window falls on page 1 of the file. See
        # https://www.intelliprint.net/docs/choose-a-content-strategy
        if recipients:
            fields["recipients"] = [
                {"address": {
                    "name": r.name, "line": r.line,
                    "postcode": r.postcode, "country": r.country,
                }}
                for r in recipients
            ]
        if reference:
            fields["reference"] = reference
        if options.get("confidential"):
            fields["confidential"] = True
        if options.get("background_first"):
            fields.setdefault("background", {})["first_page"] = options["background_first"]
        if options.get("background_other"):
            fields.setdefault("background", {})["other_pages"] = options["background_other"]

        file_path = None
        if isinstance(source, Path) or (isinstance(source, str) and source.startswith("@")):
            file_path = Path(str(source).lstrip("@"))
            if not file_path.exists():
                raise IntelliprintError(f"No such file: {file_path}")
        else:
            fields["content"] = source

        payload = self._request("POST", "/prints", fields=fields, file_path=file_path)
        return self._to_draft(payload, service)

    def retrieve_draft(self, draft_id: str) -> Draft:
        payload = self.retrieve(draft_id)
        service = self._reverse_service((payload.get("postage") or {}).get("service", ""))
        return self._to_draft(payload, service)

    def confirm(self, draft_id: str) -> Draft:
        """Commit a drafted job. This is the step that spends money."""
        payload = self._request("POST", f"/prints/{draft_id}", fields={"confirmed": True})
        service = self._reverse_service(
            (payload.get("postage") or {}).get("service", "")
        )
        return self._to_draft(payload, service)

    def cancel(self, draft_id: str) -> Cancellation:
        """DELETE /prints/{id}.

        On an unconfirmed job this deletes it whole (202, `deleted: true`). On
        a confirmed job it cancels every letter still `waiting_to_print` and
        refunds those; letters already printing or later carry on (200, the
        print object). See https://www.intelliprint.net/docs/cancelling-print-jobs
        """
        try:
            payload = self._request("DELETE", f"/prints/{draft_id}")
        except IntelliprintError as exc:
            if exc.status != 400:
                raise
            raise IntelliprintError(
                f"Intelliprint cancelled nothing on {draft_id}. Only letters still "
                "waiting to print can be cancelled. Check each letter with: "
                f"pennyblack status {draft_id}\n  Intelliprint said: {exc.body or ''}".rstrip(),
                status=exc.status, body=exc.body,
            ) from exc
        if payload.get("deleted"):
            return Cancellation(id=payload.get("id", draft_id), deleted=True, raw=payload)
        return Cancellation(id=payload.get("id", draft_id), deleted=False,
                            letters=self._mailings(payload), raw=payload,
                            testmode=_testmode(payload))

    def retrieve(self, print_id: str) -> dict:
        return self._request("GET", f"/prints/{print_id}")

    def fetch_document(self, draft: Draft) -> bytes:
        """Download the preview PDF. Signed URL, valid about an hour, so this
        has to happen at send time or not at all."""
        url = draft.preview_url
        if not url:
            return None
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "pennyblack (+https://github.com/dbhq-uk/pennyblack-skill)")
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = resp.read()
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            return None
        # A signed link that has expired returns an error page, not a PDF.
        # Keeping that as evidence would be worse than keeping nothing.
        return data if data[:5] == b"%PDF-" else None

    def status(self, print_id: str) -> list:
        return self._mailings(self.retrieve(print_id))

    def _mailings(self, payload: dict) -> list:
        out = []
        testmode = _testmode(payload)
        for letter in payload.get("letters") or []:
            returned = letter.get("returned") or {}
            out.append(Mailing(
                id=letter.get("id", ""),
                status=letter.get("status", "unknown"),
                service=self._reverse_service(letter.get("postage_service", "")),
                tracking_number=letter.get("tracking_number") or None,
                recipient=(letter.get("address") or {}).get("name"),
                shipped_date=letter.get("shipped_date"),
                returned_reason=returned.get("reason") or None,
                returned_date=returned.get("date") or None,
                raw=letter,
                testmode=testmode,
            ))
        return out
