import boto3
import botocore
from flask import Flask, Response, redirect, render_template, request, url_for

from s3_web_browser.s3 import list_objects, parse_responses
from s3_web_browser.models import db, Connection


def register_routes(app: Flask) -> None:  # noqa:C901
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
            region = request.form.get("region", "eu-central-1")
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
    def delete_connection(id: int) -> Response:
        conn = Connection.query.get_or_404(id)
        db.session.delete(conn)
        db.session.commit()
        return redirect(url_for("index"))

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

    @app.route("/c/<int:connection_id>/download/buckets/<bucket_name>/<path:path>")
    def download_file(connection_id: int, bucket_name: str, path: str) -> Response:
        conn = Connection.query.get_or_404(connection_id)
        s3_client = boto3.client("s3", **conn.to_boto3_kwargs())
        url = s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": path},
            ExpiresIn=3600,
        )
        return redirect(url)
