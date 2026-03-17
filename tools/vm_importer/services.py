import os
import boto3
import math
import time
import logging
from typing import List, Optional, Dict, Any, Callable
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

class MultipartUploader:
    """Handles S3 multipart uploads for large VM image files."""
    # 10 MB Part Size
    PART_SIZE = 10 * 1024 * 1024 

    def __init__(self, s3_client, bucket: str):
        self.s3 = s3_client
        self.bucket = bucket

    def upload_file(self, file_path: str, key: str, progress_callback: Optional[Callable[[int], None]] = None, abort_check: Optional[Callable[[], bool]] = None) -> bool:
        """
        Uploads a file using multipart upload.
        """
        file_size = os.path.getsize(file_path)
        logger.info(f"Starting upload of {file_path} ({file_size} bytes) to s3://{self.bucket}/{key}")

        upload_id = None
        try:
            # 1. Create Multipart Upload
            mpu = self.s3.create_multipart_upload(Bucket=self.bucket, Key=key)
            upload_id = mpu["UploadId"]
            parts = []

            # 2. Upload Parts
            part_count = math.ceil(file_size / self.PART_SIZE)
            
            with open(file_path, "rb") as f:
                for i in range(part_count):
                    # Check for cancellation
                    if abort_check and abort_check():
                        logger.warning("Upload cancelled by user.")
                        self.s3.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
                        return False

                    part_number = i + 1
                    data = f.read(self.PART_SIZE)
                    
                    response = self.s3.upload_part(
                        Bucket=self.bucket,
                        Key=key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=data
                    )
                    
                    parts.append({"PartNumber": part_number, "ETag": response["ETag"]})
                    
                    if progress_callback:
                        percent = int((part_number / part_count) * 100)
                        progress_callback(percent)
                    
                    logger.debug(f"Uploaded part {part_number}/{part_count}")

            # 3. Complete Multipart Upload
            self.s3.complete_multipart_upload(
                Bucket=self.bucket,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts}
            )
            logger.info("Multipart upload completed successfully.")
            return True

        except Exception as e:
            logger.error(f"Upload failed: {e}")
            if upload_id:
                try:
                    self.s3.abort_multipart_upload(Bucket=self.bucket, Key=key, UploadId=upload_id)
                except:
                    pass
            return False

class VmImportOrchestrator:
    """Orchestrates the VM import workflow: S3 upload → EC2 import-image task."""
    def __init__(self, ec2_client, s3_client):
        self.ec2 = ec2_client
        self.uploader = None # initialized per task if needed? or pass client
        self.s3_client = s3_client

    def upload_and_import(self, file_path: str, bucket_name: str, description: str, 
                         progress_cb: Optional[Callable[[str, int], None]] = None,
                         abort_check: Optional[Callable[[], bool]] = None,
                         boot_mode: str = 'legacy-bios',
                         platform: str = 'Windows',
                         license_type: str = 'BYOL',
                         architecture: str = 'x86_64') -> Optional[str]:
        """
        Uploads image and starts import task.
        """
        filename = os.path.basename(file_path)
        s3_key = f"imports/{filename}"

        # Step 1: Upload
        if progress_cb: progress_cb("Uploading", 0)
        uploader = MultipartUploader(self.s3_client, bucket_name)
        
        def _upload_prog(p):
            if progress_cb: progress_cb(f"Uploading {p}%", p)
            
        success = uploader.upload_file(file_path, s3_key, _upload_prog, abort_check)
        if not success:
            raise Exception("Upload failed (Check logs or network).")

        # Step 2: Import Image
        if progress_cb: progress_cb("Starting Import Task", 100)
        
        ext = os.path.splitext(filename)[1].lower().strip('.') 
        if ext == 'vhd': ext = 'vhd' 
        if ext == 'vhdx': ext = 'vhdx'
        
        disk_containers = [
            {
                "Description": description,
                "Format": ext,
                "UserBucket": {
                    "S3Bucket": bucket_name,
                    "S3Key": s3_key
                }
            }
        ]
        
        # Tags for the Import Task
        tags = [
            {'Key': 'CreatedBy', 'Value': 'AWS_Tool_Import'},
            {'Key': 'OriginalFile', 'Value': filename},
            {'Key': 'Name', 'Value': description[:127]} 
        ]

        response = self.ec2.import_image(
            Description=description,
            DiskContainers=disk_containers,
            LicenseType=license_type,
            BootMode=boot_mode,
            Platform=platform,
            Architecture=architecture,
            TagSpecifications=[
                {
                    'ResourceType': 'import-image-task',
                    'Tags': tags
                }
            ]
        )
        
        task_id = response["ImportTaskId"]
        logger.info(f"Import task started: {task_id}")
        return task_id

    def check_status(self, task_id: str) -> Dict[str, Any]:
        """
        Polls status of a task.
        """
        try:
            response = self.ec2.describe_import_image_tasks(ImportTaskIds=[task_id])
            if response["ImportImageTasks"]:
                task = response["ImportImageTasks"][0]
                return {
                    "Status": task["Status"],
                    "StatusMessage": task.get("StatusMessage", ""),
                    "Progress": task.get("Progress", "0"),
                    "ImageId": task.get("ImageId")
                }
            return {"Status": "unknown"}
        except ClientError as e:
            logger.error(f"Error checking status: {e}")
            return {"Status": "error", "Message": str(e)}
