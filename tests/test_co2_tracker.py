import os
import time
import unittest
from unittest import mock

import responses
import requests

from co2_tracker.co2_tracker import CO2Tracker, track_co2
from co2_tracker.external import CloudMetadata
from tests.testdata import (
    GEO_METADATA_CANADA,
    TWO_GPU_DETAILS_RESPONSE,
)
from tests.testutils import get_test_app_config


def heavy_computation(run_time_secs: int = 3):
    end_time: float = time.time() + run_time_secs  # Run for `run_time_secs` seconds
    while time.time() < end_time:
        pass


@mock.patch("co2_tracker.external.is_gpu_details_available", return_value=True)
@mock.patch(
    "co2_tracker.external.get_gpu_details", return_value=TWO_GPU_DETAILS_RESPONSE,
)
@mock.patch(
    "co2_tracker.co2_tracker.CO2Tracker._get_cloud_metadata",
    return_value=CloudMetadata(provider=None, region=None),
)
@mock.patch("co2_tracker.co2_tracker.BaseCO2Tracker._get_config")
class TestCO2Tracker(unittest.TestCase):
    def setUp(self) -> None:
        self.app_config = get_test_app_config()
        self.project_name = "project_foo"
        self.emissions_file_path = os.path.join(
            os.getcwd(), f"{self.project_name}.emissions"
        )

    def tearDown(self) -> None:
        if os.path.isfile(self.emissions_file_path):
            os.remove(self.emissions_file_path)  # delete test artifact if it exists.

    @responses.activate
    def test_co2_tracker_TWO_GPU_PRIVATE_INFRA_CANADA(
        self,
        mocked_get_config,
        mocked_env_cloud_details,
        mocked_get_gpu_details,
        mocked_is_gpu_details_available,
    ):
        # GIVEN
        mocked_get_config.return_value = self.app_config
        responses.add(
            responses.GET,
            "https://get.geojs.io/v1/ip/geo.json",
            json=GEO_METADATA_CANADA,
            status=200,
        )
        tracker = CO2Tracker(measure_power_secs=1, save_to_file=False)

        # WHEN
        tracker.start()
        heavy_computation()
        emissions = tracker.stop()

        # THEN
        self.assertEqual(
            3, mocked_get_gpu_details.call_count
        )  # 2 times in 5 seconds + once for init = 3
        self.assertEqual(1, mocked_is_gpu_details_available.call_count)
        self.assertEqual(1, len(responses.calls))
        self.assertEqual(
            "https://get.geojs.io/v1/ip/geo.json", responses.calls[0].request.url
        )
        assert isinstance(emissions, float)
        self.assertAlmostEqual(emissions, 6.262572537957655e-05, places=2)

    @mock.patch("co2_tracker.external.requests.get")
    def test_co2_tracker_timeout(
        self,
        mocked_requests_get,
        mocked_get_config,
        mocked_env_cloud_details,
        mocked_get_gpu_details,
        mocked_is_gpu_details_available,
    ):
        # GIVEN
        mocked_get_config.return_value = self.app_config

        def raise_timeout_exception(*args, **kwargs):
            raise requests.exceptions.Timeout()

        mocked_requests_get.side_effect = raise_timeout_exception

        tracker = CO2Tracker(measure_power_secs=1, save_to_file=False)

        # WHEN
        tracker.start()
        heavy_computation(run_time_secs=2)
        emissions = tracker.stop()
        self.assertEqual(1, mocked_requests_get.call_count)
        self.assertAlmostEqual(1.1037980397280433e-05, emissions, places=2)

    @responses.activate
    def test_decorator_ONLINE_NO_ARGS(
        self,
        mocked_get_config,
        mocked_env_cloud_details,
        mocked_get_gpu_details,
        mocked_is_gpu_details_available,
    ):

        # GIVEN
        mocked_get_config.return_value = self.app_config
        responses.add(
            responses.GET,
            "https://get.geojs.io/v1/ip/geo.json",
            json=GEO_METADATA_CANADA,
            status=200,
        )

        # WHEN
        @track_co2(project_name=self.project_name)
        def dummy_train_model():
            return 42

        dummy_train_model()

        # THEN
        self.verify_output_file(self.emissions_file_path)

    @responses.activate
    def test_decorator_ONLINE_WITH_ARGS(
        self,
        mocked_get_config,
        mocked_env_cloud_details,
        mocked_get_gpu_details,
        mocked_is_gpu_details_available,
    ):
        # GIVEN
        mocked_get_config.return_value = self.app_config
        responses.add(
            responses.GET,
            "https://get.geojs.io/v1/ip/geo.json",
            json=GEO_METADATA_CANADA,
            status=200,
        )

        # WHEN
        @track_co2(project_name=self.project_name, output_dir=".")
        def dummy_train_model():
            return 42

        dummy_train_model()

        # THEN
        self.verify_output_file(self.emissions_file_path)

    def test_decorator_OFFLINE_NO_COUNTRY(
        self,
        mocked_get_config,
        mocked_env_cloud_details,
        mocked_get_gpu_details,
        mocked_is_gpu_details_available,
    ):
        # WHEN

        @track_co2(offline=True)
        def dummy_train_model():
            return 42

        self.assertRaises(Exception, dummy_train_model)

    def test_decorator_OFFLINE_WITH_ARGS(
        self,
        mocked_get_config,
        mocked_get_cloud_metadata,
        mocked_get_gpu_details,
        mocked_is_gpu_details_available,
    ):
        # GIVEN
        mocked_get_config.return_value = self.app_config

        @track_co2(offline=True, country="Canada", project_name=self.project_name)
        def dummy_train_model():
            return 42

        dummy_train_model()
        self.verify_output_file(self.emissions_file_path)

    def verify_output_file(self, file_path: str) -> None:
        with open(file_path, "r") as f:
            lines = [line.rstrip() for line in f]
        assert len(lines) == 2