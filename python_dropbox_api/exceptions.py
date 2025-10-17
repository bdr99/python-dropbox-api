class DropboxFileOrFolderNotFoundException(Exception):
    """Raised when a file or folder is not found."""

    def __init__(self, status):
        """Initialize exception."""
        super().__init__(status)
        self.status = status


class DropboxAuthException(Exception):
    """Raised when a Dropbox authentication exception occurs."""

    def __init__(self, status):
        """Initialize exception."""
        super().__init__(status)
        self.status = status


class DropboxUnknownException(Exception):
    """Raised when an unknown Dropbox error occurs."""

    def __init__(self, status):
        """Initialize exception."""
        super().__init__(status)
        self.status = status
