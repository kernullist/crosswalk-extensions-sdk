# Copyright 2014 The Chromium Authors. All rights reserved.
# Use of this source code is governed by a BSD-style license that can be
# found in the LICENSE file.

import random
import unittest

from telemetry.perf_tests_helper import FlattenList
import telemetry.timeline.async_slice as tracing_async_slice
import telemetry.timeline.bounds as timeline_bounds
from telemetry.timeline import model
from telemetry.util.statistics import DivideIfPossibleOrZero
from telemetry.web_perf.metrics.rendering_stats import (
    BEGIN_COMP_NAME,
    BEGIN_SCROLL_UPDATE_COMP_NAME,
    END_COMP_NAME,
    FORWARD_SCROLL_UPDATE_COMP_NAME,
    GESTURE_SCROLL_UPDATE_EVENT_NAME,
    ORIGINAL_COMP_NAME,
    SCROLL_UPDATE_EVENT_NAME,
    UI_COMP_NAME)
from telemetry.web_perf.metrics.rendering_stats import (
    ComputeInputEventLatencies)
from telemetry.web_perf.metrics.rendering_stats import GetInputLatencyEvents
from telemetry.web_perf.metrics.rendering_stats import HasRenderingStats
from telemetry.web_perf.metrics.rendering_stats import RenderingStats


class MockTimer(object):
  """A mock timer class which can generate random durations.

  An instance of this class is used as a global timer to generate random
  durations for stats and consistent timestamps for all mock trace events.
  The unit of time is milliseconds.
  """

  def __init__(self):
    self.milliseconds = 0

  def Advance(self, low=0.1, high=1):
    delta = random.uniform(low, high)
    self.milliseconds += delta
    return delta

  def AdvanceAndGet(self, low=0.1, high=1):
    self.Advance(low, high)
    return self.milliseconds


class ReferenceRenderingStats(object):
  """ Stores expected data for comparison with actual RenderingStats """

  def __init__(self):
    self.frame_timestamps = []
    self.frame_times = []
    self.approximated_pixel_percentages = []

  def AppendNewRange(self):
    self.frame_timestamps.append([])
    self.frame_times.append([])
    self.approximated_pixel_percentages.append([])


class ReferenceInputLatencyStats(object):
  """ Stores expected data for comparison with actual input latency stats """

  def __init__(self):
    self.input_event_latency = []
    self.input_event = []


def AddSurfaceFlingerStats(mock_timer, thread, first_frame,
                           ref_stats=None):
  """ Adds a random surface flinger stats event.

  thread: The timeline model thread to which the event will be added.
  first_frame: Is this the first frame within the bounds of an action?
  ref_stats: A ReferenceRenderingStats object to record expected values.
  """
  # Create randonm data and timestap for impl thread rendering stats.
  data = {'frame_count': 1,
          'refresh_period': 16.6666}
  timestamp = mock_timer.AdvanceAndGet()

  # Add a slice with the event data to the given thread.
  thread.PushCompleteSlice(
      'SurfaceFlinger', 'vsync_before',
      timestamp, duration=0.0, thread_timestamp=None, thread_duration=None,
      args={'data': data})

  if not ref_stats:
    return

  # Add timestamp only if a frame was output
  if data['frame_count'] == 1:
    if not first_frame:
      # Add frame_time if this is not the first frame in within the bounds of an
      # action.
      prev_timestamp = ref_stats.frame_timestamps[-1][-1]
      ref_stats.frame_times[-1].append(round(timestamp - prev_timestamp, 2))
    ref_stats.frame_timestamps[-1].append(timestamp)


def AddDisplayRenderingStats(mock_timer, thread, first_frame,
                             ref_stats=None):
  """ Adds a random display rendering stats event.

  thread: The timeline model thread to which the event will be added.
  first_frame: Is this the first frame within the bounds of an action?
  ref_stats: A ReferenceRenderingStats object to record expected values.
  """
  # Create randonm data and timestap for main thread rendering stats.
  data = {'frame_count': 1}
  timestamp = mock_timer.AdvanceAndGet()

  # Add a slice with the event data to the given thread.
  thread.PushCompleteSlice(
      'benchmark', 'BenchmarkInstrumentation::DisplayRenderingStats',
      timestamp, duration=0.0, thread_timestamp=None, thread_duration=None,
      args={'data': data})

  if not ref_stats:
    return

  # Add timestamp only if a frame was output
  if not first_frame:
    # Add frame_time if this is not the first frame in within the bounds of an
    # action.
    prev_timestamp = ref_stats.frame_timestamps[-1][-1]
    ref_stats.frame_times[-1].append(round(timestamp - prev_timestamp, 2))
  ref_stats.frame_timestamps[-1].append(timestamp)


def AddImplThreadRenderingStats(mock_timer, thread, first_frame,
                                ref_stats=None):
  """ Adds a random impl thread rendering stats event.

  thread: The timeline model thread to which the event will be added.
  first_frame: Is this the first frame within the bounds of an action?
  ref_stats: A ReferenceRenderingStats object to record expected values.
  """
  # Create randonm data and timestap for impl thread rendering stats.
  data = {'frame_count': 1,
          'visible_content_area': random.uniform(0, 100),
          'approximated_visible_content_area': random.uniform(0, 5)}
  timestamp = mock_timer.AdvanceAndGet()

  # Add a slice with the event data to the given thread.
  thread.PushCompleteSlice(
      'benchmark', 'BenchmarkInstrumentation::ImplThreadRenderingStats',
      timestamp, duration=0.0, thread_timestamp=None, thread_duration=None,
      args={'data': data})

  if not ref_stats:
    return

  # Add timestamp only if a frame was output
  if data['frame_count'] == 1:
    if not first_frame:
      # Add frame_time if this is not the first frame in within the bounds of an
      # action.
      prev_timestamp = ref_stats.frame_timestamps[-1][-1]
      ref_stats.frame_times[-1].append(round(timestamp - prev_timestamp, 2))
    ref_stats.frame_timestamps[-1].append(timestamp)

  ref_stats.approximated_pixel_percentages[-1].append(
      round(DivideIfPossibleOrZero(data['approximated_visible_content_area'],
                                   data['visible_content_area']) * 100.0, 3))


def AddInputLatencyStats(mock_timer, start_thread, end_thread,
                         ref_latency_stats=None):
  """ Adds a random input latency stats event.

  start_thread: The start thread on which the async slice is added.
  end_thread: The end thread on which the async slice is ended.
  ref_latency_stats: A ReferenceInputLatencyStats object for expected values.
  """

  original_comp_time = mock_timer.AdvanceAndGet(2, 4) * 1000.0
  ui_comp_time = mock_timer.AdvanceAndGet(2, 4) * 1000.0
  begin_comp_time = mock_timer.AdvanceAndGet(2, 4) * 1000.0
  forward_comp_time = mock_timer.AdvanceAndGet(2, 4) * 1000.0
  end_comp_time = mock_timer.AdvanceAndGet(10, 20) * 1000.0

  data = {ORIGINAL_COMP_NAME: {'time': original_comp_time},
          UI_COMP_NAME: {'time': ui_comp_time},
          BEGIN_COMP_NAME: {'time': begin_comp_time},
          END_COMP_NAME: {'time': end_comp_time}}

  timestamp = mock_timer.AdvanceAndGet(2, 4)

  async_slice = tracing_async_slice.AsyncSlice(
      'benchmark', 'InputLatency', timestamp)

  async_sub_slice = tracing_async_slice.AsyncSlice(
      'benchmark', GESTURE_SCROLL_UPDATE_EVENT_NAME, timestamp)
  async_sub_slice.args = {'data': data}
  async_sub_slice.parent_slice = async_slice
  async_sub_slice.start_thread = start_thread
  async_sub_slice.end_thread = end_thread

  async_slice.sub_slices.append(async_sub_slice)
  async_slice.start_thread = start_thread
  async_slice.end_thread = end_thread
  start_thread.AddAsyncSlice(async_slice)

  # Add scroll update latency info.
  scroll_update_data = {
      BEGIN_SCROLL_UPDATE_COMP_NAME: {'time': begin_comp_time},
      FORWARD_SCROLL_UPDATE_COMP_NAME: {'time': forward_comp_time},
      END_COMP_NAME: {'time': end_comp_time}}

  scroll_async_slice = tracing_async_slice.AsyncSlice(
      'benchmark', 'InputLatency', timestamp)

  scroll_async_sub_slice = tracing_async_slice.AsyncSlice(
      'benchmark', SCROLL_UPDATE_EVENT_NAME, timestamp)
  scroll_async_sub_slice.args = {'data': scroll_update_data}
  scroll_async_sub_slice.parent_slice = scroll_async_slice
  scroll_async_sub_slice.start_thread = start_thread
  scroll_async_sub_slice.end_thread = end_thread

  scroll_async_slice.sub_slices.append(scroll_async_sub_slice)
  scroll_async_slice.start_thread = start_thread
  scroll_async_slice.end_thread = end_thread
  start_thread.AddAsyncSlice(scroll_async_slice)

  # Also add some dummy frame statistics so we can feed the resulting timeline
  # to RenderingStats.
  AddImplThreadRenderingStats(mock_timer, end_thread, False)

  if not ref_latency_stats:
    return

  ref_latency_stats.input_event.append(async_sub_slice)
  ref_latency_stats.input_event.append(scroll_async_sub_slice)
  ref_latency_stats.input_event_latency.append((
      GESTURE_SCROLL_UPDATE_EVENT_NAME,
      (data[END_COMP_NAME]['time'] -
       data[ORIGINAL_COMP_NAME]['time']) / 1000.0))
  ref_latency_stats.input_event_latency.append((
      SCROLL_UPDATE_EVENT_NAME,
      (scroll_update_data[END_COMP_NAME]['time'] -
       scroll_update_data[BEGIN_SCROLL_UPDATE_COMP_NAME]['time']) / 1000.0))


class RenderingStatsUnitTest(unittest.TestCase):

  def testHasRenderingStats(self):
    timeline = model.TimelineModel()
    timer = MockTimer()

    # A process without rendering stats
    process_without_stats = timeline.GetOrCreateProcess(pid=1)
    thread_without_stats = process_without_stats.GetOrCreateThread(tid=11)
    process_without_stats.FinalizeImport()
    self.assertFalse(HasRenderingStats(thread_without_stats))

    # A process with rendering stats, but no frames in them
    process_without_frames = timeline.GetOrCreateProcess(pid=2)
    thread_without_frames = process_without_frames.GetOrCreateThread(tid=21)
    process_without_frames.FinalizeImport()
    self.assertFalse(HasRenderingStats(thread_without_frames))

    # A process with rendering stats and frames in them
    process_with_frames = timeline.GetOrCreateProcess(pid=3)
    thread_with_frames = process_with_frames.GetOrCreateThread(tid=31)
    AddImplThreadRenderingStats(timer, thread_with_frames, True, None)
    process_with_frames.FinalizeImport()
    self.assertTrue(HasRenderingStats(thread_with_frames))

  def testBothSurfaceFlingerAndDisplayStats(self):
    timeline = model.TimelineModel()
    timer = MockTimer()

    ref_stats = ReferenceRenderingStats()
    ref_stats.AppendNewRange()
    surface_flinger = timeline.GetOrCreateProcess(pid=4)
    surface_flinger.name = 'SurfaceFlinger'
    surface_flinger_thread = surface_flinger.GetOrCreateThread(tid=41)
    renderer = timeline.GetOrCreateProcess(pid=2)
    browser = timeline.GetOrCreateProcess(pid=3)
    browser_main = browser.GetOrCreateThread(tid=31)
    browser_main.BeginSlice('webkit.console', 'ActionA',
                            timer.AdvanceAndGet(2, 4), '')

    # Create SurfaceFlinger stats and display rendering stats.
    for i in xrange(0, 10):
      first = (i == 0)
      AddSurfaceFlingerStats(timer, surface_flinger_thread, first, ref_stats)
      timer.Advance(2, 4)

    for i in xrange(0, 10):
      first = (i == 0)
      AddDisplayRenderingStats(timer, browser_main, first, None)
      timer.Advance(5, 10)

    browser_main.EndSlice(timer.AdvanceAndGet())
    timer.Advance(2, 4)

    browser.FinalizeImport()
    renderer.FinalizeImport()
    timeline_markers = timeline.FindTimelineMarkers(['ActionA'])
    timeline_ranges = [timeline_bounds.Bounds.CreateFromEvent(marker)
                       for marker in timeline_markers]
    stats = RenderingStats(renderer, browser, surface_flinger, timeline_ranges)

    # Compare rendering stats to reference - Only SurfaceFlinger stats should
    # count
    self.assertEquals(stats.frame_timestamps, ref_stats.frame_timestamps)
    self.assertEquals(stats.frame_times, ref_stats.frame_times)

  def testBothDisplayAndImplStats(self):
    timeline = model.TimelineModel()
    timer = MockTimer()

    ref_stats = ReferenceRenderingStats()
    ref_stats.AppendNewRange()
    renderer = timeline.GetOrCreateProcess(pid=2)
    browser = timeline.GetOrCreateProcess(pid=3)
    browser_main = browser.GetOrCreateThread(tid=31)
    browser_main.BeginSlice('webkit.console', 'ActionA',
                            timer.AdvanceAndGet(2, 4), '')

    # Create main, impl, and display rendering stats.
    for i in xrange(0, 10):
      first = (i == 0)
      AddImplThreadRenderingStats(timer, browser_main, first, None)
      timer.Advance(2, 4)

    for i in xrange(0, 10):
      first = (i == 0)
      AddDisplayRenderingStats(timer, browser_main, first, ref_stats)
      timer.Advance(5, 10)

    browser_main.EndSlice(timer.AdvanceAndGet())
    timer.Advance(2, 4)

    browser.FinalizeImport()
    renderer.FinalizeImport()
    timeline_markers = timeline.FindTimelineMarkers(['ActionA'])
    timeline_ranges = [timeline_bounds.Bounds.CreateFromEvent(marker)
                       for marker in timeline_markers]
    stats = RenderingStats(renderer, browser, None, timeline_ranges)

    # Compare rendering stats to reference - Only display stats should count
    self.assertEquals(stats.frame_timestamps, ref_stats.frame_timestamps)
    self.assertEquals(stats.frame_times, ref_stats.frame_times)

  def testRangeWithoutFrames(self):
    timer = MockTimer()
    timeline = model.TimelineModel()

    # Create a renderer process, with a main thread and impl thread.
    renderer = timeline.GetOrCreateProcess(pid=2)
    renderer_main = renderer.GetOrCreateThread(tid=21)
    renderer_compositor = renderer.GetOrCreateThread(tid=22)

    # Create 10 main and impl rendering stats events for Action A.
    renderer_main.BeginSlice('webkit.console', 'ActionA',
                             timer.AdvanceAndGet(2, 4), '')
    for i in xrange(0, 10):
      first = (i == 0)
      AddImplThreadRenderingStats(timer, renderer_compositor, first, None)
    renderer_main.EndSlice(timer.AdvanceAndGet(2, 4))
    timer.Advance(2, 4)

    # Create 5 main and impl rendering stats events not within any action.
    for i in xrange(0, 5):
      first = (i == 0)
      AddImplThreadRenderingStats(timer, renderer_compositor, first, None)

    # Create Action B without any frames. This should trigger
    # NotEnoughFramesError when the RenderingStats object is created.
    renderer_main.BeginSlice('webkit.console', 'ActionB',
                             timer.AdvanceAndGet(2, 4), '')
    renderer_main.EndSlice(timer.AdvanceAndGet(2, 4))

    renderer.FinalizeImport()

    timeline_markers = timeline.FindTimelineMarkers(['ActionA', 'ActionB'])
    timeline_ranges = [timeline_bounds.Bounds.CreateFromEvent(marker)
                       for marker in timeline_markers]

    stats = RenderingStats(renderer, None, None, timeline_ranges)
    self.assertEquals(0, len(stats.frame_timestamps[1]))

  def testFromTimeline(self):
    timeline = model.TimelineModel()

    # Create a browser process and a renderer process, and a main thread and
    # impl thread for each.
    browser = timeline.GetOrCreateProcess(pid=1)
    browser_compositor = browser.GetOrCreateThread(tid=12)
    renderer = timeline.GetOrCreateProcess(pid=2)
    renderer_main = renderer.GetOrCreateThread(tid=21)
    renderer_compositor = renderer.GetOrCreateThread(tid=22)

    timer = MockTimer()
    renderer_ref_stats = ReferenceRenderingStats()
    browser_ref_stats = ReferenceRenderingStats()

    # Create 10 main and impl rendering stats events for Action A.
    renderer_main.BeginSlice('webkit.console', 'ActionA',
                             timer.AdvanceAndGet(2, 4), '')
    renderer_ref_stats.AppendNewRange()
    browser_ref_stats.AppendNewRange()
    for i in xrange(0, 10):
      first = (i == 0)
      AddImplThreadRenderingStats(
          timer, renderer_compositor, first, renderer_ref_stats)
      AddImplThreadRenderingStats(
          timer, browser_compositor, first, browser_ref_stats)
    renderer_main.EndSlice(timer.AdvanceAndGet(2, 4))

    # Create 5 main and impl rendering stats events not within any action.
    for i in xrange(0, 5):
      first = (i == 0)
      AddImplThreadRenderingStats(timer, renderer_compositor, first, None)
      AddImplThreadRenderingStats(timer, browser_compositor, first, None)

    # Create 10 main and impl rendering stats events for Action B.
    renderer_main.BeginSlice('webkit.console', 'ActionB',
                             timer.AdvanceAndGet(2, 4), '')
    renderer_ref_stats.AppendNewRange()
    browser_ref_stats.AppendNewRange()
    for i in xrange(0, 10):
      first = (i == 0)
      AddImplThreadRenderingStats(
          timer, renderer_compositor, first, renderer_ref_stats)
      AddImplThreadRenderingStats(
          timer, browser_compositor, first, browser_ref_stats)
    renderer_main.EndSlice(timer.AdvanceAndGet(2, 4))

    # Create 10 main and impl rendering stats events for Action A.
    renderer_main.BeginSlice('webkit.console', 'ActionA',
                             timer.AdvanceAndGet(2, 4), '')
    renderer_ref_stats.AppendNewRange()
    browser_ref_stats.AppendNewRange()
    for i in xrange(0, 10):
      first = (i == 0)
      AddImplThreadRenderingStats(
          timer, renderer_compositor, first, renderer_ref_stats)
      AddImplThreadRenderingStats(
          timer, browser_compositor, first, browser_ref_stats)
    renderer_main.EndSlice(timer.AdvanceAndGet(2, 4))
    timer.Advance(2, 4)

    browser.FinalizeImport()
    renderer.FinalizeImport()

    timeline_markers = timeline.FindTimelineMarkers(
        ['ActionA', 'ActionB', 'ActionA'])
    timeline_ranges = [timeline_bounds.Bounds.CreateFromEvent(marker)
                       for marker in timeline_markers]
    stats = RenderingStats(renderer, browser, None, timeline_ranges)

    # Compare rendering stats to reference.
    self.assertEquals(stats.frame_timestamps,
                      browser_ref_stats.frame_timestamps)
    self.assertEquals(stats.frame_times, browser_ref_stats.frame_times)
    self.assertEquals(stats.approximated_pixel_percentages,
                      renderer_ref_stats.approximated_pixel_percentages)

  def testInputLatencyFromTimeline(self):
    timeline = model.TimelineModel()

    # Create a browser process and a renderer process.
    browser = timeline.GetOrCreateProcess(pid=1)
    browser_main = browser.GetOrCreateThread(tid=11)
    renderer = timeline.GetOrCreateProcess(pid=2)
    renderer_main = renderer.GetOrCreateThread(tid=21)

    timer = MockTimer()
    ref_latency = ReferenceInputLatencyStats()

    # Create 10 input latency stats events for Action A.
    renderer_main.BeginSlice('webkit.console', 'ActionA',
                             timer.AdvanceAndGet(2, 4), '')
    for _ in xrange(0, 10):
      AddInputLatencyStats(timer, browser_main, renderer_main, ref_latency)
    renderer_main.EndSlice(timer.AdvanceAndGet(2, 4))

    # Create 5 input latency stats events not within any action.
    timer.Advance(2, 4)
    for _ in xrange(0, 5):
      AddInputLatencyStats(timer, browser_main, renderer_main, None)

    # Create 10 input latency stats events for Action B.
    renderer_main.BeginSlice('webkit.console', 'ActionB',
                             timer.AdvanceAndGet(2, 4), '')
    for _ in xrange(0, 10):
      AddInputLatencyStats(timer, browser_main, renderer_main, ref_latency)
    renderer_main.EndSlice(timer.AdvanceAndGet(2, 4))

    # Create 10 input latency stats events for Action A.
    renderer_main.BeginSlice('webkit.console', 'ActionA',
                             timer.AdvanceAndGet(2, 4), '')
    for _ in xrange(0, 10):
      AddInputLatencyStats(timer, browser_main, renderer_main, ref_latency)
    renderer_main.EndSlice(timer.AdvanceAndGet(2, 4))

    browser.FinalizeImport()
    renderer.FinalizeImport()

    input_events = []

    timeline_markers = timeline.FindTimelineMarkers(
        ['ActionA', 'ActionB', 'ActionA'])
    timeline_ranges = [timeline_bounds.Bounds.CreateFromEvent(marker)
                       for marker in timeline_markers]
    for timeline_range in timeline_ranges:
      if timeline_range.is_empty:
        continue
      input_events.extend(GetInputLatencyEvents(browser, timeline_range))

    self.assertEquals(input_events, ref_latency.input_event)
    input_event_latency_result = ComputeInputEventLatencies(input_events)
    self.assertEquals(input_event_latency_result,
                      ref_latency.input_event_latency)

    stats = RenderingStats(renderer, browser, None, timeline_ranges)
    self.assertEquals(FlattenList(stats.input_event_latency), [
        latency for name, latency in ref_latency.input_event_latency
        if name != SCROLL_UPDATE_EVENT_NAME])
    self.assertEquals(FlattenList(stats.scroll_update_latency), [
        latency for name, latency in ref_latency.input_event_latency
        if name == SCROLL_UPDATE_EVENT_NAME])
    self.assertEquals(FlattenList(stats.gesture_scroll_update_latency), [
        latency for name, latency in ref_latency.input_event_latency
        if name == GESTURE_SCROLL_UPDATE_EVENT_NAME])
