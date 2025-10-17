from collections.abc import AsyncIterator
import json

from aiohttp import ClientResponse

from .auth import Auth
from .exceptions import (
    DropboxAuthException,
    DropboxFileOrFolderNotFoundException,
    DropboxUnknownException,
)
from .models import (
    AccountInfo,
    FileOrFolderInfo,
    PropertyField,
    PropertyFieldValue,
    PropertyGroup,
    PropertyTemplate,
)

DROPBOX_API_BASE_URL = "https://api.dropboxapi.com"
CONTENT_API_BASE_URL = "https://content.dropboxapi.com"


def parse_property_groups(property_groups: list[dict]) -> list[PropertyGroup]:
    """Parse the property groups from the response."""
    return [
        PropertyGroup(
            template_id=group["template_id"],
            fields=[
                PropertyFieldValue(name=field["name"], value=field["value"])
                for field in group["fields"]
            ],
        )
        for group in property_groups
    ]


async def handle_common_errors(response: ClientResponse) -> None:
    """Handle common errors."""
    response_json = await response.json()

    error_summary = response_json.get("error_summary")

    if error_summary is not None:
        if error_summary.startswith("invalid_access_token/"):
            raise DropboxAuthException("Unauthorized")
        if error_summary.startswith("path/not_found/"):
            raise DropboxFileOrFolderNotFoundException("File or folder not found")

    response.raise_for_status()


class DropboxAPIClient:
    """Lightweight Dropbox API client."""

    def __init__(self, auth: Auth) -> None:
        """Initialize the API client."""
        self._websession = auth.websession
        self._auth = auth

    async def get_account_info(self) -> AccountInfo:
        """Get information about the current account.

        Returns:
            AccountInfo containing account_id, email, and display_name.
        """
        try:
            access_token = await self._auth.async_get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "",
            }

            url = f"{DROPBOX_API_BASE_URL}/2/users/get_current_account"

            async with self._websession.post(url, headers=headers) as response:
                await handle_common_errors(response)

                response_json = await response.json()

                return AccountInfo(
                    account_id=response_json["account_id"],
                    email=response_json["email"],
                    display_name=response_json["name"]["display_name"],
                )
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err

    async def list_folder(
        self, path: str, include_property_groups: list[str] | None = None
    ) -> list[FileOrFolderInfo]:
        """List the contents of a folder with pagination support."""
        try:
            access_token = await self._auth.async_get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # Initial request data
            data = {
                "include_deleted": False,
                "include_has_explicit_shared_members": False,
                "include_media_info": False,
                "include_mounted_folders": True,
                "include_non_downloadable_files": False,
                "path": path,
                "recursive": False,
            }

            if include_property_groups is not None:
                data["include_property_groups"] = {
                    ".tag": "filter_some",
                    "filter_some": include_property_groups,
                }

            all_entries = []
            cursor = None
            has_more = True

            while has_more:
                # Use list_folder endpoint for first request, list_folder/continue for subsequent ones
                if cursor is None:
                    url = f"{DROPBOX_API_BASE_URL}/2/files/list_folder"
                    request_data = data
                else:
                    url = f"{DROPBOX_API_BASE_URL}/2/files/list_folder/continue"
                    request_data = {"cursor": cursor}

                async with self._websession.post(
                    url, headers=headers, json=request_data
                ) as response:
                    await handle_common_errors(response)

                    response_json = await response.json()

                    # Add entries from this page to our collection
                    page_entries = [
                        FileOrFolderInfo(
                            is_folder=file[".tag"] == "folder",
                            name=file["name"],
                            size=file["size"] if file[".tag"] == "file" else None,
                            property_groups=parse_property_groups(
                                file["property_groups"]
                            )
                            if "property_groups" in file
                            else None,
                        )
                        for file in response_json["entries"]
                    ]
                    all_entries.extend(page_entries)

                    # Check if there are more pages
                    has_more = response_json.get("has_more", False)
                    cursor = response_json.get("cursor")

            return all_entries
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err

    async def get_metadata(
        self, path: str, include_property_groups: list[str] | None = None
    ) -> FileOrFolderInfo:
        """Get metadata for a file or folder.

        Args:
            path: The Dropbox path to get metadata for.
            include_property_groups: Optional list of property group template IDs to include.

        Returns:
            FileOrFolderInfo containing metadata for the file or folder.
        """
        try:
            access_token = await self._auth.async_get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            data = {
                "include_deleted": False,
                "include_has_explicit_shared_members": False,
                "include_media_info": False,
                "path": path,
            }

            if include_property_groups is not None:
                data["include_property_groups"] = {
                    ".tag": "filter_some",
                    "filter_some": include_property_groups,
                }

            url = f"{DROPBOX_API_BASE_URL}/2/files/get_metadata"

            async with self._websession.post(
                url, headers=headers, json=data
            ) as response:
                await handle_common_errors(response)

                response_json = await response.json()

                return FileOrFolderInfo(
                    is_folder=response_json[".tag"] == "folder",
                    name=response_json["name"],
                    size=response_json["size"]
                    if response_json[".tag"] == "file"
                    else None,
                    property_groups=parse_property_groups(
                        response_json["property_groups"]
                    )
                    if "property_groups" in response_json
                    else None,
                )
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err

    async def upload_file(
        self,
        path: str,
        file_stream: AsyncIterator[bytes],
        property_groups: list[PropertyGroup] | None = None,
    ) -> None:
        """Upload a file to Dropbox using chunked upload sessions.

        Args:
            path: The Dropbox path where the file should be uploaded.
            file_stream: An async iterator of bytes to upload.
            property_groups: Optional list of property groups to attach to the uploaded file.
        """
        try:
            CHUNK_SIZE = 16 * 1024 * 1024  # 16MB chunks

            # Always use chunked upload approach
            await self._upload_file_chunked(
                CONTENT_API_BASE_URL, path, file_stream, CHUNK_SIZE, property_groups
            )
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err

    async def _upload_file_chunked(
        self,
        content_api_url: str,
        path: str,
        file_stream: AsyncIterator[bytes],
        chunk_size: int,
        property_groups: list[PropertyGroup] | None = None,
    ) -> None:
        """Upload a file using chunked upload sessions, streaming chunks without loading entire file into memory."""
        session_id = None
        offset = 0
        is_first_chunk = True

        # Buffer to accumulate chunks until we have enough for a full chunk
        buffer = b""

        async for data_chunk in file_stream:
            buffer += data_chunk

            # Process full chunks from the buffer
            while len(buffer) >= chunk_size:
                chunk_data = buffer[:chunk_size]
                buffer = buffer[chunk_size:]

                if is_first_chunk:
                    # Start upload session with first chunk
                    session_id = await self._start_upload_session(
                        content_api_url, chunk_data
                    )
                    is_first_chunk = False
                else:
                    # Append chunk to existing session
                    await self._append_to_upload_session(
                        content_api_url, session_id, offset, chunk_data
                    )

                offset += len(chunk_data)

        # Handle remaining data in buffer (final partial chunk)
        if buffer:
            if is_first_chunk:
                # If this is the only chunk, start session with it
                session_id = await self._start_upload_session(content_api_url, buffer)
            else:
                # Append final chunk
                await self._append_to_upload_session(
                    content_api_url, session_id, offset, buffer
                )
            offset += len(buffer)

        # Finish upload session
        await self._finish_upload_session(
            content_api_url, session_id, offset, path, property_groups
        )

    async def _start_upload_session(
        self, content_api_url: str, chunk_data: bytes
    ) -> str:
        """Start an upload session with the first chunk."""
        access_token = await self._auth.async_get_access_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Dropbox-API-Arg": json.dumps({"close": False}),
            "Content-Type": "application/octet-stream",
        }

        async with self._websession.post(
            f"{content_api_url}/2/files/upload_session/start",
            headers=headers,
            data=chunk_data,
        ) as response:
            await handle_common_errors(response)

            response_json = await response.json()
            return response_json["session_id"]

    async def _append_to_upload_session(
        self, content_api_url: str, session_id: str, offset: int, chunk_data: bytes
    ) -> None:
        """Append a chunk to an existing upload session."""
        access_token = await self._auth.async_get_access_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Dropbox-API-Arg": json.dumps(
                {
                    "close": False,
                    "cursor": {
                        "session_id": session_id,
                        "offset": offset,
                    },
                }
            ),
            "Content-Type": "application/octet-stream",
        }

        async with self._websession.post(
            f"{content_api_url}/2/files/upload_session/append_v2",
            headers=headers,
            data=chunk_data,
        ) as response:
            await handle_common_errors(response)

    async def _finish_upload_session(
        self,
        content_api_url: str,
        session_id: str,
        total_size: int,
        path: str,
        property_groups: list[PropertyGroup] | None = None,
    ) -> None:
        """Finish an upload session."""
        # Build commit data
        commit_data = {
            "path": path,
            "mode": "add",
            "autorename": True,
            "mute": True,
            "strict_conflict": True,
        }

        # Add property groups if provided
        if property_groups:
            commit_data["property_groups"] = [
                {
                    "template_id": group.template_id,
                    "fields": [
                        {"name": field.name, "value": field.value}
                        for field in group.fields
                    ],
                }
                for group in property_groups
            ]

        access_token = await self._auth.async_get_access_token()

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Dropbox-API-Arg": json.dumps(
                {
                    "commit": commit_data,
                    "cursor": {
                        "session_id": session_id,
                        "offset": total_size,
                    },
                }
            ),
            "Content-Type": "application/octet-stream",
        }

        # Send empty data for finish request
        async with self._websession.post(
            f"{content_api_url}/2/files/upload_session/finish",
            headers=headers,
            data=b"",
        ) as response:
            await handle_common_errors(response)

    async def download_file(self, path: str) -> AsyncIterator[bytes]:
        """Download a file from Dropbox as an async byte stream.

        Args:
            path: The Dropbox path to the file to download.

        Yields:
            Chunks of file content as bytes.
        """
        try:
            access_token = await self._auth.async_get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Dropbox-API-Arg": json.dumps({"path": path}),
            }

            url = f"{CONTENT_API_BASE_URL}/2/files/download"
            chunk_size = 1024 * 1024  # 1MB

            async with self._websession.post(url, headers=headers) as response:
                response.raise_for_status()
                async for chunk in response.content.iter_chunked(chunk_size):
                    if chunk:
                        yield chunk
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err

    async def create_folder(self, path: str) -> FileOrFolderInfo:
        """Create a folder in Dropbox.

        Args:
            path: The Dropbox path where the folder should be created.

        Returns:
            FileOrFolderInfo containing metadata for the created folder.
        """
        try:
            access_token = await self._auth.async_get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            url = f"{DROPBOX_API_BASE_URL}/2/files/create_folder_v2"
            payload = {
                "path": path,
                "autorename": False,
            }

            async with self._websession.post(
                url, headers=headers, json=payload
            ) as response:
                await handle_common_errors(response)
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err

    async def delete_file(self, path: str) -> None:
        """Delete a file (moves to Dropbox trash).

        Args:
            path: The Dropbox path of the file to delete.
        """
        try:
            access_token = await self._auth.async_get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            url = f"{DROPBOX_API_BASE_URL}/2/files/delete_v2"
            payload = {"path": path}

            async with self._websession.post(
                url, headers=headers, json=payload
            ) as response:
                await handle_common_errors(response)
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err

    async def list_property_templates(self) -> list[str]:
        """List property group templates for the current user.

        Returns:
            A list of template IDs for property group templates.
        """
        try:
            access_token = await self._auth.async_get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "",
            }

            url = f"{DROPBOX_API_BASE_URL}/2/file_properties/templates/list_for_user"

            async with self._websession.post(url, headers=headers) as response:
                await handle_common_errors(response)

                response_json = await response.json()
                return response_json["template_ids"]
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err

    async def add_property_template(self, template: PropertyTemplate) -> str:
        """Add a property group template for the current user.

        Args:
            template: The property template to add.

        Returns:
            A string containing the template ID.
        """
        try:
            access_token = await self._auth.async_get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            # Convert the template to the format expected by the API
            data = {
                "name": template.name,
                "description": template.description,
                "fields": [
                    {
                        "name": field.name,
                        "description": field.description,
                        "type": field.type,
                    }
                    for field in template.fields
                ],
            }

            url = f"{DROPBOX_API_BASE_URL}/2/file_properties/templates/add_for_user"

            async with self._websession.post(
                url, headers=headers, json=data
            ) as response:
                await handle_common_errors(response)

                response_json = await response.json()
                return response_json["template_id"]
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err

    async def remove_property_template(self, template_id: str) -> None:
        """Remove a property group template for the current user.

        Args:
            template_id: The ID of the property template to remove.
        """
        try:
            access_token = await self._auth.async_get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            data = {"template_id": template_id}

            url = f"{DROPBOX_API_BASE_URL}/2/file_properties/templates/remove_for_user"

            async with self._websession.post(
                url, headers=headers, json=data
            ) as response:
                await handle_common_errors(response)
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err

    async def get_property_template(self, template_id: str) -> PropertyTemplate:
        """Get a property group template for the current user.

        Args:
            template_id: The ID of the property template to get.

        Returns:
            The PropertyTemplate.
        """
        try:
            access_token = await self._auth.async_get_access_token()

            headers = {
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            }

            data = {"template_id": template_id}

            url = f"{DROPBOX_API_BASE_URL}/2/file_properties/templates/get_for_user"

            async with self._websession.post(
                url, headers=headers, json=data
            ) as response:
                await handle_common_errors(response)

                response_json = await response.json()

                fields = [
                    PropertyField(
                        name=field["name"],
                        description=field["description"],
                        type=field["type"][".tag"]
                        if isinstance(field["type"], dict)
                        else field["type"],
                    )
                    for field in response_json["fields"]
                ]

                return PropertyTemplate(
                    name=response_json["name"],
                    description=response_json["description"],
                    fields=fields,
                )
        except (DropboxAuthException, DropboxFileOrFolderNotFoundException):
            raise
        except Exception as err:
            raise DropboxUnknownException(str(err)) from err
