import pandas as pd
import datetime

from ..shared.plot.plotting import timeseries_analysis_plot

from ..shared.io import NameList, StreamsFile
from ..shared.io.utility import buildConfigFullPath

from ..shared.generalized_reader.generalized_reader \
    import open_multifile_dataset

from ..shared.timekeeping.utility import stringToDatetime, \
    clampToNumpyDatetime64


def sst_timeseries(config, streamMap=None, variableMap=None):
    """
    Performs analysis of the time-series output of sea-surface temperature
    (SST).

    config is an instance of MpasAnalysisConfigParser containing configuration
    options.

    If present, streamMap is a dictionary of MPAS-O stream names that map to
    their mpas_analysis counterparts.

    If present, variableMap is a dictionary of MPAS-O variable names that map
    to their mpas_analysis counterparts.

    Author: Xylar Asay-Davis, Milena Veneziani
    Last Modified: 02/02/2017
    """

    # Define/read in general variables
    print '  Load SST data...'
    # read parameters from config file
    inDirectory = config.get('input', 'baseDirectory')

    streamsFileName = config.get('input', 'oceanStreamsFileName')
    streams = StreamsFile(streamsFileName, streamsdir=inDirectory)

    namelistFileName = config.get('input', 'oceanNamelistFileName')
    namelist = NameList(namelistFileName, path=inDirectory)

    calendar = namelist.get('config_calendar_type')

    # get a list of timeSeriesStats output files from the streams file,
    # reading only those that are between the start and end dates
    startDate = config.get('timeSeries', 'startDate')
    endDate = config.get('timeSeries', 'endDate')
    streamName = streams.find_stream(streamMap['timeSeriesStats'])
    fileNames = streams.readpath(streamName, startDate=startDate,
                                 endDate=endDate,  calendar=calendar)
    print 'Reading files {} through {}'.format(fileNames[0], fileNames[-1])

    mainRunName = config.get('runs', 'mainRunName')
    preprocessedReferenceRunName = config.get('runs',
                                              'preprocessedReferenceRunName')
    preprocessedInputDirectory = config.get('oceanPreprocessedReference',
                                            'baseDirectory')

    plotsDirectory = buildConfigFullPath(config, 'output', 'plotsSubdirectory')

    yearOffset = config.getint('time', 'yearOffset')

    movingAveragePoints = config.getint('timeSeriesSST', 'movingAveragePoints')

    regions = config.getExpression('regions', 'regions')
    plotTitles = config.getExpression('regions', 'plotTitles')
    regionIndicesToPlot = config.getExpression('timeSeriesSST',
                                               'regionIndicesToPlot')

    # Load data:
    varList = ['avgSurfaceTemperature']
    ds = open_multifile_dataset(fileNames=fileNames,
                                calendar=calendar,
                                timeVariableName='Time',
                                variableList=varList,
                                variableMap=variableMap,
                                startDate=startDate,
                                endDate=endDate,
                                yearOffset=yearOffset)

    timeStart = clampToNumpyDatetime64(stringToDatetime(startDate), yearOffset)
    timeEnd = clampToNumpyDatetime64(stringToDatetime(endDate), yearOffset)
    # select only the data in the specified range of years
    ds = ds.sel(Time=slice(timeStart, timeEnd))

    SSTregions = ds.avgSurfaceTemperature

    yearStart = (pd.to_datetime(ds.Time.min().values)).year
    yearEnd = (pd.to_datetime(ds.Time.max().values)).year
    timeStart = datetime.datetime(yearStart, 1, 1)
    timeEnd = datetime.datetime(yearEnd, 12, 31)

    if preprocessedReferenceRunName != 'None':
        print '  Load in SST for a preprocesses reference run...'
        inFilesPreprocessed = '{}/SST.{}.year*.nc'.format(
            preprocessedInputDirectory, preprocessedReferenceRunName)
        dsPreprocessed = open_multifile_dataset(fileNames=inFilesPreprocessed,
                                                calendar=calendar,
                                                timeVariableName='xtime',
                                                yearOffset=yearOffset)
        yearEndPreprocessed = \
            (pd.to_datetime(dsPreprocessed.Time.max().values)).year
        if yearStart <= yearEndPreprocessed:
            dsPreprocessedTimeSlice = \
                dsPreprocessed.sel(Time=slice(timeStart, timeEnd))
        else:
            print '   Warning: Preprocessed time series ends before the ' \
                'timeSeries startYear and will not be plotted.'
            preprocessedReferenceRunName = 'None'

    print '  Make plots...'
    for index in range(len(regionIndicesToPlot)):
        regionIndex = regionIndicesToPlot[index]

        title = plotTitles[regionIndex]
        title = 'SST, %s, %s (r-)' % (title, mainRunName)
        xLabel = 'Time [years]'
        yLabel = '[$^\circ$ C]'

        SST = SSTregions[:, regionIndex]

        if preprocessedReferenceRunName != 'None':
            figureName = '{}/sst_{}_{}_{}.png'.format(
                plotsDirectory, regions[regionIndex], mainRunName,
                preprocessedReferenceRunName)
            SST_v0 = dsPreprocessedTimeSlice.SST

            title = '{}\n {} (b-)'.format(title, preprocessedReferenceRunName)
            timeseries_analysis_plot(config, [SST, SST_v0],
                                     movingAveragePoints,
                                     title, xLabel, yLabel, figureName,
                                     lineStyles=['r-', 'b-'],
                                     lineWidths=[1.2, 1.2])
        else:
            figureName = '{}/sst_{}_{}.png'.format(plotsDirectory,
                                                   regions[regionIndex],
                                                   mainRunName)
            timeseries_analysis_plot(config, [SST], movingAveragePoints, title,
                                     xLabel, yLabel, figureName,
                                     lineStyles=['r-'], lineWidths=[1.2])
