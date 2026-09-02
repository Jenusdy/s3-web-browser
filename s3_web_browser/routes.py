import tempfile
import typing
import zipfile

import boto3
import botocore
from flask import Flask, Response, redirect, render_template, request, send_file, url_for

from s3_web_browser.models import Connection, db
from s3_web_browser.s3 import list_objects, parse_responses


def register_routes(app: Flask) -> None:  # noqa: C901, PLR0915
    @app.errorhandler(404)
    def page_not_found(_e: Exception) -> tuple[str, int]:
        return render_template("error.html", error="The requested page was not found."), 404

    @app.errorhandler(500)
    def internal_server_error(e: Exception) -> tuple[str, int]:
        return render_template("error.html", error=f"Internal Server Error: {e}"), 500

    @app.errorhandler(Exception)
    def handle_exception(e: Exception) -> tuple[str, int]:
        return render_template("error.html", error=f"An unexpected error occurred: {e}"), 500

    @app.route("/", methods=["GET"])
    def index() -> str:
        connections = Connection.query.all()
        return render_template("index.html", connections=connections)

    @app.route("/connections/new", methods=["GET", "POST"])
    def new_connection() -> str | Response:
        if request.method == "POST":
            name = request.form.get("name")
            endpoint_url = request.form.get("endpoint_url")
            access_key_id = request.form.get("access_key_id")
            secret_access_key = request.form.get("secret_access_key")
            
            region_input = request.form.get("region")
            region = region_input.strip() if region_input else "eu-central-1"
            
            default_bucket = request.form.get("default_bucket")

            conn = Connection(
                name=name,
                endpoint_url=endpoint_url or None,
                access_key_id=access_key_id or None,
                secret_access_key=secret_access_key or None,
                region=region,
                default_bucket=default_bucket or None
            )
            db.session.add(conn)
            db.session.commit()
            return redirect(url_for("index"))
        return render_template("connection_form.html")

    @app.route("/connections/<int:id>/delete", methods=["POST"])
    def delete_connection(id: int) -> Response:  # noqa: A002
        conn = Connection.query.get_or_404(id)
        db.session.delete(conn)
        db.session.commit()
        return redirect(url_for("index"))

    @app.route("/connections/<int:id>/edit", methods=["GET", "POST"])
    def edit_connection(id: int) -> str | Response:  # noqa: A002
        conn = Connection.query.get_or_404(id)
        if request.method == "POST":
            conn.name = request.form.get("name")
            conn.endpoint_url = request.form.get("endpoint_url") or None
            conn.access_key_id = request.form.get("access_key_id") or None
            
            new_secret = request.form.get("secret_access_key")
            if new_secret:
                conn.secret_access_key = new_secret
                
            region_input = request.form.get("region")
            conn.region = region_input.strip() if region_input else "eu-central-1"
            
            conn.default_bucket = request.form.get("default_bucket") or None
            
            db.session.commit()
            return redirect(url_for("index"))
        return render_template("connection_form.html", connection=conn)

    @app.route("/c/<int:connection_id>/buckets")
    def buckets(connection_id: int) -> str | Response:
        conn = Connection.query.get_or_404(connection_id)
        if conn.default_bucket:
            return redirect(url_for("view_bucket", connection_id=connection_id, bucket_name=conn.default_bucket))

        try:
            s3 = boto3.resource("s3", **conn.to_boto3_kwargs())
            all_buckets = list(s3.buckets.all())
            return render_template("buckets.html", buckets=all_buckets, connection=conn)
        except botocore.exceptions.ClientError as e:
            if e.response["Error"]["Code"] == "AccessDenied":
                return render_template(
                    "error.html",
                    error="You do not have permission to access all buckets. Please configure a default bucket for this connection."
                )
            return render_template("error.html", error=f"An unknown error occurred: {e}")

    @app.route("/c/<int:connection_id>/search/buckets/<bucket_name>", defaults={"path": ""})
    @app.route("/c/<int:connection_id>/search/buckets/<bucket_name>/<path:path>")
    def search_bucket(connection_id: int, bucket_name: str, path: str) -> str:
        conn = Connection.query.get_or_404(connection_id)
        page = request.args.get("page", 1, type=int)
        items_per_page = app.config["PAGE_ITEMS"]
        s3_client = boto3.client("s3", **conn.to_boto3_kwargs())
        paginator = s3_client.get_paginator("list_objects_v2")
        all_entries = []
        all_prefixes = []

        try:
            for page_iterator in paginator.paginate(Bucket=bucket_name, Prefix=path):
                if "Contents" in page_iterator:
                    all_entries.extend(
                        {"Key": item["Key"], "Size": item["Size"], "LastModified": item["LastModified"]}
                        for item in page_iterator["Contents"]
                        if not item["Key"].endswith("/")
                    )

            for page_iterator in paginator.paginate(Bucket=bucket_name, Prefix=path, Delimiter="/"):
                if "CommonPrefixes" in page_iterator:
                    all_prefixes.extend(page_iterator["CommonPrefixes"])

            response = {"Contents": all_entries, "CommonPrefixes": all_prefixes}
            search_param = request.args.get("search", "")
            contents = parse_responses([response], search_param)

            total_items = len(contents)
            total_pages = (total_items + items_per_page - 1) // items_per_page if total_items else 1
            page = max(1, min(page, total_pages))
            start_idx = (page - 1) * items_per_page
            end_idx = start_idx + items_per_page
            paginated_contents = contents[start_idx:end_idx]

            return render_template(
                "bucket_contents.html",
                contents=paginated_contents,
                bucket_name=bucket_name,
                path=path,
                search_param=search_param,
                current_page=page,
                total_pages=total_pages,
                connection=conn,
            )

        except botocore.exceptions.ClientError as e:
            match e.response["Error"]["Code"]:
                case "AccessDenied":
                    return render_template("error.html", error="You do not have permission to access this bucket.")
                case "NoSuchBucket":
                    return render_template("error.html", error="The specified bucket does not exist.")
                case _:
                    return render_template("error.html", error=f"An unknown error occurred: {e}")

    @app.route("/c/<int:connection_id>/buckets/<bucket_name>", defaults={"path": ""})
    @app.route("/c/<int:connection_id>/buckets/<bucket_name>/<path:path>")
    def view_bucket(connection_id: int, bucket_name: str, path: str) -> str | Response:
        conn = Connection.query.get_or_404(connection_id)
        search_param = request.args.get("search", "")
        if search_param:
            return redirect(
                request.url_root.rstrip("/")
                + f"/c/{connection_id}/search/buckets/{bucket_name}/{path}".rstrip("/")
                + f"?search={search_param}"
            )

        page = request.args.get("page", 1, type=int)
        items_per_page = app.config["PAGE_ITEMS"]
        s3_client = boto3.client("s3", **conn.to_boto3_kwargs())

        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            total_objects = 0
            continuation_token = None
            for pages_seen, page_iterator in enumerate(
                paginator.paginate(
                    Bucket=bucket_name,
                    Prefix=path,
                    Delimiter="/",
                    PaginationConfig={"PageSize": items_per_page},
                ),
                start=1,
            ):
                if "CommonPrefixes" in page_iterator:
                    total_objects += len(page_iterator["CommonPrefixes"])
                if "Contents" in page_iterator:
                    total_objects += sum(1 for obj in page_iterator["Contents"] if not obj["Key"].endswith("/"))

                if pages_seen == page - 1:
                    continuation_token = page_iterator.get("NextContinuationToken")

            total_pages = (total_objects + items_per_page - 1) // items_per_page if total_objects else 1
            page = max(1, min(page, total_pages))

            response = list_objects(s3_client, bucket_name, path, items_per_page, "/", continuation_token)
            contents = parse_responses([response], "")

            return render_template(
                "bucket_contents.html",
                contents=contents,
                bucket_name=bucket_name,
                path=path,
                search_param="",
                current_page=page,
                total_pages=total_pages,
                connection=conn,
            )

        except botocore.exceptions.ClientError as e:
            match e.response["Error"]["Code"]:
                case "AccessDenied":
                    return render_template("error.html", error="You do not have permission to access this bucket.")
                case "NoSuchBucket":
                    return render_template("error.html", error="The specified bucket does not exist.")
                case _:
                    return render_template("error.html", error=f"An unknown error occurred: {e}")

    @app.route("/c/<int:connection_id>/size/buckets/<bucket_name>", defaults={"path": ""})
    @app.route("/c/<int:connection_id>/size/buckets/<bucket_name>/<path:path>")
    def get_bucket_size(connection_id: int, bucket_name: str, path: str) -> Response:
        conn = Connection.query.get_or_404(connection_id)
        s3_client = boto3.client("s3", **conn.to_boto3_kwargs())
        
        import humanize
        from flask import jsonify

        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            
            # Calculate bucket size
            bucket_size = 0
            for page in paginator.paginate(Bucket=bucket_name):
                if "Contents" in page:
                    bucket_size += sum(item["Size"] for item in page["Contents"] if not item["Key"].endswith("/"))
            
            # Calculate folder size if path is provided
            folder_size = None
            if path:
                if not path.endswith("/"):
                    path += "/"
                folder_size = 0
                for page in paginator.paginate(Bucket=bucket_name, Prefix=path):
                    if "Contents" in page:
                        folder_size += sum(item["Size"] for item in page["Contents"] if not item["Key"].endswith("/"))
                        
            response_data = {
                "bucket_size_human": humanize.naturalsize(bucket_size),
                "bucket_size_bytes": bucket_size
            }
            if folder_size is not None:
                response_data["folder_size_human"] = humanize.naturalsize(folder_size)
                response_data["folder_size_bytes"] = folder_size
                
            return jsonify(response_data)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    @app.route("/c/<int:connection_id>/download/buckets/<bucket_name>/<path:path>")
    def download_file(connection_id: int, bucket_name: str, path: str) -> Response:
        conn = Connection.query.get_or_404(connection_id)
        s3_client = boto3.client("s3", **conn.to_boto3_kwargs())

        try:
            s3_object = s3_client.get_object(Bucket=bucket_name, Key=path)

            def generate() -> typing.Iterator[bytes]:
                yield from s3_object["Body"].iter_chunks(chunk_size=4096)

            return Response(
                generate(),
                mimetype=s3_object.get("ContentType", "application/octet-stream"),
                headers={
                    "Content-Disposition": f"attachment; filename={path.rsplit('/', maxsplit=1)[-1]}",
                    "Content-Length": str(s3_object["ContentLength"])
                }
            )
        except Exception as e:  # noqa: BLE001
            return render_template("error.html", error=f"Error downloading file: {e}")

    @app.route("/c/<int:connection_id>/upload/buckets/<bucket_name>", methods=["POST"])
    @app.route("/c/<int:connection_id>/upload/buckets/<bucket_name>/<path:path>", methods=["POST"])
    def upload_file(connection_id: int, bucket_name: str, path: str = "") -> Response:
        if "file" not in request.files:
            return Response("No file part", status=400)

        file = request.files["file"]
        if not file or file.filename == "":
            return Response("No selected file", status=400)

        conn = Connection.query.get_or_404(connection_id)
        s3_client = boto3.client("s3", **conn.to_boto3_kwargs())

        try:
            filename = file.filename
            if path:
                if not path.endswith("/"):
                    path = path + "/"
                object_key = f"{path}{filename}"
            else:
                object_key = filename

            s3_client.upload_fileobj(file, bucket_name, object_key)
            return Response("Upload successful", status=200)
        except Exception as e:  # noqa: BLE001
            return Response(f"Upload failed: {e}", status=500)

    @app.route("/c/<int:connection_id>/delete/buckets/<bucket_name>/<path:path>", methods=["POST"])
    def delete_file(connection_id: int, bucket_name: str, path: str) -> Response:
        conn = Connection.query.get_or_404(connection_id)
        s3_client = boto3.client("s3", **conn.to_boto3_kwargs())

        try:
            s3_client.delete_object(Bucket=bucket_name, Key=path)
            return Response("Deleted", status=200)
        except Exception as e:  # noqa: BLE001
            return Response(f"Failed to delete: {e}", status=500)

    @app.route("/c/<int:connection_id>/download-zip/buckets/<bucket_name>/<path:path>")
    def download_zip(connection_id: int, bucket_name: str, path: str) -> Response:
        conn = Connection.query.get_or_404(connection_id)
        s3_client = boto3.client("s3", **conn.to_boto3_kwargs())

        if not path.endswith("/"):
            path += "/"

        temp_file = tempfile.NamedTemporaryFile(suffix=".zip")  # noqa: SIM115

        try:
            with zipfile.ZipFile(temp_file, "w", zipfile.ZIP_DEFLATED) as zf:
                paginator = s3_client.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=bucket_name, Prefix=path):
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        if key.endswith("/"):
                            continue

                        s3_object = s3_client.get_object(Bucket=bucket_name, Key=key)
                        zip_path = key[len(path):] if key.startswith(path) else key
                        if not zip_path:
                            zip_path = key.split("/")[-1]

                        with zf.open(zip_path, "w") as f:
                            for chunk in s3_object["Body"].iter_chunks(chunk_size=65536):
                                f.write(chunk)

            temp_file.seek(0)
            folder_name = path.rstrip("/").split("/")[-1]
            response = send_file(
                temp_file,
                mimetype="application/zip",
                as_attachment=True,
                download_name=f"{folder_name}.zip"
            )
            response.set_cookie("download_started", "1", max_age=120, path="/")
            return response  # noqa: TRY300
        except Exception as e:  # noqa: BLE001
            temp_file.close()
            return render_template("error.html", error=f"Error generating ZIP: {e}")
