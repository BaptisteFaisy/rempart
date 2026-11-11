"""S3 Bucket and CloudFront Distribution stack for the Rempart portal."""

from __future__ import annotations

import aws_cdk as cdk
import aws_cdk.aws_cloudfront as cloudfront
import aws_cdk.aws_cloudfront_origins as origins
import aws_cdk.aws_s3 as s3
from constructs import Construct


class PortalStack(cdk.Stack):
    """Provisions S3 hosting bucket and CloudFront distribution for the static web portal."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.bucket = s3.Bucket(
            self,
            "PortalBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=True,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
        self.distribution = self._create_distribution()
        cdk.CfnOutput(
            self,
            "PortalBucketName",
            value=self.bucket.bucket_name,
            description="Portal S3 Bucket Name",
        )
        cdk.CfnOutput(
            self,
            "PortalDomainName",
            value=self.distribution.distribution_domain_name,
            description="Portal CloudFront Domain Name",
        )

    def _create_distribution(self) -> cloudfront.Distribution:
        spa_errors = [
            cloudfront.ErrorResponse(
                http_status=code,
                response_http_status=200,
                response_page_path="/index.html",
                ttl=cdk.Duration.seconds(10),
            )
            for code in (403, 404)
        ]
        return cloudfront.Distribution(
            self,
            "PortalDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(self.bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            default_root_object="index.html",
            error_responses=spa_errors,
            price_class=cloudfront.PriceClass.PRICE_CLASS_100,
        )
