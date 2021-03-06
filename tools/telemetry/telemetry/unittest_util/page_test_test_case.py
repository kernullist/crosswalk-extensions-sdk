# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

"""Provide a TestCase base class for PageTest subclasses' unittests."""

import unittest

from telemetry import benchmark
from telemetry.core import exceptions
from telemetry.core import util
from telemetry.page import page as page_module
from telemetry.page import page_set as page_set_module
from telemetry.page import page_test
from telemetry.page import test_expectations
from telemetry.results import results_options
from telemetry.unittest_util import options_for_unittests
from telemetry.user_story import user_story_runner


class BasicTestPage(page_module.Page):
  def __init__(self, url, page_set, base_dir):
    super(BasicTestPage, self).__init__(url, page_set, base_dir)

  def RunPageInteractions(self, action_runner):
    interaction = action_runner.BeginGestureInteraction('ScrollAction')
    action_runner.ScrollPage()
    interaction.End()


class EmptyMetadataForTest(benchmark.BenchmarkMetadata):
  def __init__(self):
    super(EmptyMetadataForTest, self).__init__('')


class PageTestTestCase(unittest.TestCase):
  """A base class to simplify writing unit tests for PageTest subclasses."""

  def CreatePageSetFromFileInUnittestDataDir(self, test_filename):
    ps = self.CreateEmptyPageSet()
    page = BasicTestPage('file://' + test_filename, ps, base_dir=ps.base_dir)
    ps.AddUserStory(page)
    return ps

  def CreateEmptyPageSet(self):
    base_dir = util.GetUnittestDataDir()
    ps = page_set_module.PageSet(file_path=base_dir)
    return ps

  def RunMeasurement(self, measurement, ps,
      expectations=test_expectations.TestExpectations(),
      options=None):
    """Runs a measurement against a pageset, returning the rows its outputs."""
    if options is None:
      options = options_for_unittests.GetCopy()
    assert options
    temp_parser = options.CreateParser()
    user_story_runner.AddCommandLineArgs(temp_parser)
    defaults = temp_parser.get_default_values()
    for k, v in defaults.__dict__.items():
      if hasattr(options, k):
        continue
      setattr(options, k, v)

    measurement.CustomizeBrowserOptions(options.browser_options)
    options.output_file = None
    options.output_formats = ['none']
    options.suppress_gtest_report = True
    options.output_trace_tag = None
    user_story_runner.ProcessCommandLineArgs(temp_parser, options)
    results = results_options.CreateResults(EmptyMetadataForTest(), options)
    user_story_runner.Run(measurement, ps, expectations, options, results)
    return results

  def TestTracingCleanedUp(self, measurement_class, options=None):
    ps = self.CreatePageSetFromFileInUnittestDataDir('blank.html')
    start_tracing_called = [False]
    stop_tracing_called = [False]

    class BuggyMeasurement(measurement_class):
      def __init__(self, *args, **kwargs):
        measurement_class.__init__(self, *args, **kwargs)

      # Inject fake tracing methods to tracing_controller
      def TabForPage(self, page, browser):
        ActualStartTracing = browser.platform.tracing_controller.Start
        def FakeStartTracing(*args, **kwargs):
          ActualStartTracing(*args, **kwargs)
          start_tracing_called[0] = True
          raise exceptions.IntentionalException
        browser.StartTracing = FakeStartTracing

        ActualStopTracing = browser.platform.tracing_controller.Stop
        def FakeStopTracing(*args, **kwargs):
          result = ActualStopTracing(*args, **kwargs)
          stop_tracing_called[0] = True
          return result
        browser.platform.tracing_controller.Stop = FakeStopTracing

        return measurement_class.TabForPage(self, page, browser)

    measurement = BuggyMeasurement()
    try:
      self.RunMeasurement(measurement, ps, options=options)
    except page_test.TestNotSupportedOnPlatformError:
      pass
    if start_tracing_called[0]:
      self.assertTrue(stop_tracing_called[0])
