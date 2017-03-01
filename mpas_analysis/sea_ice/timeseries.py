import xarray as xr

from ..shared.plot.plotting import timeseries_analysis_plot

from ..shared.io import NameList, StreamsFile
from ..shared.io.utility import buildConfigFullPath

from ..shared.timekeeping.utility import get_simulation_start_time, \
    date_to_days, days_to_datetime, datetime_to_days
from ..shared.timekeeping.MpasRelativeDelta import MpasRelativeDelta

from ..shared.generalized_reader.generalized_reader \
    import open_multifile_dataset
from ..shared.mpas_xarray.mpas_xarray import subset_variables


def seaice_timeseries(config, streamMap=None, variableMap=None):
    """
    Performs analysis of time series of sea-ice properties.

    config is an instance of MpasAnalysisConfigParser containing configuration
    options.

    If present, streamMap is a dictionary of MPAS-O stream names that map to
    their mpas_analysis counterparts.

    If present, variableMap is a dictionary of MPAS-O variable names that map
    to their mpas_analysis counterparts.

    Author: Xylar Asay-Davis, Milena Veneziani
    Last Modified: 02/02/2017
    """

    # read parameters from config file
    inDirectory = config.get('input', 'baseDirectory')

    namelistFileName = config.get('input', 'seaIceNamelistFileName')
    namelist = NameList(namelistFileName, path=inDirectory)

    streamsFileName = config.get('input', 'seaIceStreamsFileName')
    streams = StreamsFile(streamsFileName, streamsdir=inDirectory)

    calendar = namelist.get('config_calendar_type')
    try:
        simulationStartTime = get_simulation_start_time(streams)
    except IOError:
        # try the ocean stream instead
        oceanStreamsFileName = config.get('input', 'oceanStreamsFileName')
        oceanStreams = StreamsFile(oceanStreamsFileName,
                                   streamsdir=inDirectory)
        simulationStartTime = get_simulation_start_time(oceanStreams)

    # get a list of timeSeriesStatsMonthly output files from the streams file,
    # reading only those that are between the start and end dates
    startDate = config.get('timeSeries', 'startDate')
    endDate = config.get('timeSeries', 'endDate')
    streamName = streams.find_stream(streamMap['timeSeriesStats'])
    fileNames = streams.readpath(streamName, startDate=startDate,
                                 endDate=endDate,  calendar=calendar)
    print 'Reading files {} through {}'.format(fileNames[0], fileNames[-1])

    variableNames = ['iceAreaCell', 'iceVolumeCell']

    plotTitles = {'iceAreaCell': 'Sea-ice area',
                  'iceVolumeCell': 'Sea-ice volume',
                  'iceThickness': 'Sea-ice thickness'}

    unitsDictionary = {'iceAreaCell': '[km$^2$]',
                       'iceVolumeCell': '[10$^3$ km$^3$]',
                       'iceThickness': '[m]'}

    obsFileNames = {
        'iceAreaCell': [buildConfigFullPath(config, 'seaIceObservations',
                                            subdir)
                        for subdir in ['areaNH', 'areaSH']],
        'iceVolumeCell': [buildConfigFullPath(config, 'seaIceObservations',
                                              subdir)
                          for subdir in ['volNH', 'volSH']]}

    # Some plotting rules
    titleFontSize = config.get('timeSeriesSeaIceAreaVol', 'titleFontSize')

    mainRunName = config.get('runs', 'mainRunName')
    preprocessedReferenceRunName = config.get('runs',
                                              'preprocessedReferenceRunName')
    preprocessedReferenceDirectory = config.get('seaIcePreprocessedReference',
                                                'baseDirectory')

    compareWithObservations = config.getboolean('timeSeriesSeaIceAreaVol',
                                                'compareWithObservations')

    plotsDirectory = buildConfigFullPath(config, 'output', 'plotsSubdirectory')

    movingAveragePoints = config.getint('timeSeriesSeaIceAreaVol',
                                        'movingAveragePoints')

    # first, check for a sea-ice restart file
    try:
        restartFile = streams.readpath('restart')[0]
    except ValueError:
        # get an ocean restart file, since no sea-ice restart exists
        try:
            oceanStreamsFileName = config.get('input', 'oceanStreamsFileName')
            oceanStreams = StreamsFile(oceanStreamsFileName,
                                       streamsdir=inDirectory)
            restartFile = oceanStreams.readpath('restart')[0]
        except ValueError:
            raise IOError('No MPAS-O or MPAS-Seaice restart file found: need '
                          'at least one restart file for seaice_timeseries '
                          'calculation')

    print '  Load sea-ice data...'
    # Load mesh
    dsMesh = xr.open_dataset(restartFile)
    dsMesh = subset_variables(dsMesh,
                              variableList=['lonCell', 'latCell', 'areaCell'])

    # Load data
    ds = open_multifile_dataset(fileNames=fileNames,
                                calendar=calendar,
                                simulationStartTime=simulationStartTime,
                                timeVariableName='Time',
                                variableList=['iceAreaCell',
                                              'iceVolumeCell'],
                                variableMap=variableMap,
                                startDate=startDate,
                                endDate=endDate)

    # handle the case where the "mesh" file has a spurious time dimension
    if 'Time' in dsMesh.keys():
        dsMesh = dsMesh.drop('Time')
    ds = ds.merge(dsMesh)

    yearStart = days_to_datetime(ds.Time.min(), calendar=calendar).year
    yearEnd = days_to_datetime(ds.Time.max(), calendar=calendar).year
    timeStart = date_to_days(year=yearStart, month=1, day=1,
                             calendar=calendar)
    timeEnd = date_to_days(year=yearEnd, month=12, day=31,
                           calendar=calendar)

    if preprocessedReferenceRunName != 'None':
        inFilesPreprocessed = '{}/icevol.{}.year*.nc'.format(
            preprocessedReferenceDirectory, preprocessedReferenceRunName)
        dsPreprocessed = open_multifile_dataset(fileNames=inFilesPreprocessed,
                                                calendar=calendar,
                                                timeVariableName='xtime')
        preprocessedYearEnd = days_to_datetime(dsPreprocessed.Time.max(),
                                               calendar=calendar).year
        if yearStart <= preprocessedYearEnd:
            dsPreprocessedTimeSlice = dsPreprocessed.sel(Time=slice(timeStart,
                                                                    timeEnd))
        else:
            print '   Warning: Preprocessed time series ends before the ' \
                'timeSeries startYear and will not be plotted.'
            preprocessedReferenceRunName = 'None'

    # Make Northern and Southern Hemisphere partition:
    areaCell = ds.areaCell
    maskNH = ds.latCell > 0
    maskSH = ds.latCell < 0
    areaCellNH = areaCell.where(maskNH)
    areaCellSH = areaCell.where(maskSH)

    for variableName in variableNames:
        obsFileNameNH = obsFileNames[variableName][0]
        obsFileNameSH = obsFileNames[variableName][1]
        plotTitle = plotTitles[variableName]
        units = unitsDictionary[variableName]

        print '  Compute NH and SH time series of {}...'.format(variableName)
        if variableName == 'iceThickCell':
            variableNamefull = 'iceVolumeCell'
        else:
            variableNamefull = variableName
        var = ds[variableNamefull]

        varNH = var.where(maskNH)*areaCellNH
        varSH = var.where(maskSH)*areaCellSH

        maskIceExtent = var > 0.15
        varNHIceExtent = varNH.where(maskIceExtent)
        varSHIceExtent = varSH.where(maskIceExtent)

        if variableName == 'iceAreaCell':
            varNH = varNH.sum('nCells')
            varSH = varSH.sum('nCells')
            varNH = 1e-6*varNH  # m^2 to km^2
            varSH = 1e-6*varSH  # m^2 to km^2
            varNHIceExtent = 1e-6*varNHIceExtent.sum('nCells')
            varSHIceExtent = 1e-6*varSHIceExtent.sum('nCells')
        elif variableName == 'iceVolumeCell':
            varNH = varNH.sum('nCells')
            varSH = varSH.sum('nCells')
            varNH = 1e-3*1e-9*varNH  # m^3 to 10^3 km^3
            varSH = 1e-3*1e-9*varSH  # m^3 to 10^3 km^3
        else:
            varNH = varNH.mean('nCells')/areaCellNH.mean('nCells')
            varSH = varSH.mean('nCells')/areaCellSH.mean('nCells')

        print '  Make plots...'

        xLabel = 'Time [years]'

        if preprocessedReferenceRunName != 'None':
            figureNameNH = '{}/{}NH_{}_{}.png'.format(
                plotsDirectory, variableName, mainRunName,
                preprocessedReferenceRunName)
            figureNameSH = '{}/{}SH_{}_{}.png'.format(
                plotsDirectory, variableName, mainRunName,
                preprocessedReferenceRunName)
        else:
            figureNameNH = '{}/{}NH_{}.png'.format(plotsDirectory,
                                                   variableName,
                                                   mainRunName)
            figureNameSH = '{}/{}SH_{}.png'.format(plotsDirectory,
                                                   variableName,
                                                   mainRunName)

        titleNH = '{} (NH), {} (r)'.format(plotTitle, mainRunName)
        titleSH = '{} (SH), {} (r)'.format(plotTitle, mainRunName)

        if compareWithObservations:
            if variableName == 'iceAreaCell':
                titleNH = \
                    '{}\nSSM/I observations, annual cycle (k)'.format(titleNH)
                titleSH = \
                    '{}\nSSM/I observations, annual cycle (k)'.format(titleSH)
            elif variableName == 'iceVolumeCell':
                titleNH = '{}\nPIOMAS, annual cycle (k)'.format(titleNH)
                titleSH = '{}\n'.format(titleSH)

        if preprocessedReferenceRunName != 'None':
            titleNH = '{}\n {} (b)'.format(titleNH,
                                           preprocessedReferenceRunName)
            titleSH = '{}\n {} (b)'.format(titleSH,
                                           preprocessedReferenceRunName)

        if variableName == 'iceAreaCell':

            if compareWithObservations:
                dsObs = open_multifile_dataset(fileNames=obsFileNameNH,
                                               calendar=calendar,
                                               timeVariableName='xtime')
                varNHObs = dsObs.IceArea
                varNHObs = replicate_cycle(varNH, varNHObs, calendar)

                dsObs = open_multifile_dataset(fileNames=obsFileNameSH,
                                               calendar=calendar,
                                               timeVariableName='xtime')
                varSHObs = dsObs.IceArea
                varSHObs = replicate_cycle(varSH, varSHObs, calendar)

            if preprocessedReferenceRunName != 'None':
                inFilesPreprocessed = '{}/icearea.{}.year*.nc'.format(
                    preprocessedReferenceDirectory,
                    preprocessedReferenceRunName)
                dsPreprocessed = open_multifile_dataset(
                    fileNames=inFilesPreprocessed,
                    calendar=calendar,
                    timeVariableName='xtime')
                dsPreprocessedTimeSlice = dsPreprocessed.sel(
                    Time=slice(timeStart, timeEnd))
                varNHPreprocessed = dsPreprocessedTimeSlice.icearea_nh
                varSHPreprocessed = dsPreprocessedTimeSlice.icearea_sh

        elif variableName == 'iceVolumeCell':

            if compareWithObservations:
                dsObs = open_multifile_dataset(fileNames=obsFileNameNH,
                                               calendar=calendar,
                                               timeVariableName='xtime')
                varNHObs = dsObs.IceVol
                varNHObs = replicate_cycle(varNH, varNHObs, calendar)

                varSHObs = None

            if preprocessedReferenceRunName != 'None':
                inFilesPreprocessed = '{}/icevol.{}.year*.nc'.format(
                    preprocessedReferenceDirectory,
                    preprocessedReferenceRunName)
                dsPreprocessed = open_multifile_dataset(
                    fileNames=inFilesPreprocessed,
                    calendar=calendar,
                    timeVariableName='xtime')
                dsPreprocessedTimeSlice = dsPreprocessed.sel(
                    Time=slice(timeStart, timeEnd))
                varNHPreprocessed = dsPreprocessedTimeSlice.icevolume_nh
                varSHPreprocessed = dsPreprocessedTimeSlice.icevolume_sh

        if variableName in ['iceAreaCell', 'iceVolumeCell']:
            if compareWithObservations:
                if preprocessedReferenceRunName != 'None':
                    varsNH = [varNH, varNHObs, varNHPreprocessed]
                    varsSH = [varSH, varSHObs, varSHPreprocessed]
                    lineStyles = ['r-', 'k-', 'b-']
                    lineWidths = [1.2, 1.2, 1.2]
                else:
                    # just v1 model and obs
                    varsNH = [varNH, varNHObs]
                    varsSH = [varSH, varSHObs]
                    lineStyles = ['r-', 'k-']
                    lineWidths = [1.2, 1.2]
            elif preprocessedReferenceRunName != 'None':
                # just v1 and v0 models
                varsNH = [varNH, varNHPreprocessed]
                varsSH = [varSH, varSHPreprocessed]
                lineStyles = ['r-', 'b-']
                lineWidths = [1.2, 1.2]

            if (compareWithObservations or
                    preprocessedReferenceRunName != 'None'):
                # separate plots for nothern and southern hemispheres
                timeseries_analysis_plot(config, varsNH, movingAveragePoints,
                                         titleNH,
                                         xLabel, units, figureNameNH,
                                         lineStyles=lineStyles,
                                         lineWidths=lineWidths,
                                         titleFontSize=titleFontSize)
                timeseries_analysis_plot(config, varsSH, movingAveragePoints,
                                         titleSH,
                                         xLabel, units, figureNameSH,
                                         lineStyles=lineStyles,
                                         lineWidths=lineWidths,
                                         titleFontSize=titleFontSize)
            else:
                # we will combine north and south onto a single graph
                figureName = '{}/{}.{}.png'.format(plotsDirectory, mainRunName,
                                                   variableName)
                title = '{}, NH (r), SH (k)\n{}'.format(plotTitle, mainRunName)
                timeseries_analysis_plot(config, [varNH, varSH],
                                         movingAveragePoints,
                                         title, xLabel, units, figureName,
                                         lineStyles=['r-', 'k-'],
                                         lineWidths=[1.2, 1.2],
                                         titleFontSize=titleFontSize)

        elif variableName == 'iceThickCell':

            figureName = '{}/{}.{}.png'.format(plotsDirectory, mainRunName,
                                               variableName)
            title = '{} NH (r), SH (k)\n{}'.format(plotTitle, mainRunName)
            timeseries_analysis_plot(config, [varNH, varSH],
                                     movingAveragePoints, title,
                                     xLabel, units, figureName,
                                     lineStyles=['r-', 'k-'],
                                     lineWidths=[1.2, 1.2],
                                     titleFontSize=titleFontSize)

        else:
            raise ValueError(
                'variableName variable {} not supported for plotting'.format(
                    variableName))


def replicate_cycle(ds, dsToReplicate, calendar):
    """
    Replicates a periodic time series `dsToReplicate` to cover the timeframe
    of the dataset `ds`.

    Parameters
    ----------
    ds : dataset used to find the start and end time of the replicated cycle

    dsToReplicate : dataset to replicate.  The period of the cycle is the
        length of dsToReplicate plus the time between the first two time
        values (typically one year total).

    calendar : {'gregorian', 'gregorian_noleap'}
        The name of one of the calendars supported by MPAS cores

    Returns:
    --------
    dsShift : a cyclicly repeated version of `dsToReplicte` covering the range
        of time of `ds`.

    Authors
    -------
    Xylar Asay-Davis, Milena Veneziani

    Last Modified
    -------------
    02/22/2017
    """
    dsStartTime = days_to_datetime(ds.Time.min(), calendar=calendar)
    dsEndTime = days_to_datetime(ds.Time.max(), calendar=calendar)
    repStartTime = days_to_datetime(dsToReplicate.Time.min(),
                                    calendar=calendar)
    repEndTime = days_to_datetime(dsToReplicate.Time.max(),
                                  calendar=calendar)

    repSecondTime = days_to_datetime(dsToReplicate.Time.isel(Time=1),
                                     calendar=calendar)

    period = (MpasRelativeDelta(repEndTime, repStartTime) +
              MpasRelativeDelta(repSecondTime, repStartTime))

    startIndex = 0
    while(dsStartTime > repStartTime + (startIndex+1)*period):
        startIndex += 1

    endIndex = 0
    while(dsEndTime > repEndTime + endIndex*period):
        endIndex += 1

    dsShift = dsToReplicate.copy()

    times = days_to_datetime(dsShift.Time, calendar=calendar)
    dsShift.coords['Time'] = ('Time',
                              datetime_to_days(times + startIndex*period,
                                               calendar=calendar))
    # replicate cycle:
    for cycleIndex in range(startIndex, endIndex):
        dsNew = dsToReplicate.copy()
        dsNew.coords['Time'] = ('Time',
                                datetime_to_days(times + (cycleIndex+1)*period,
                                                 calendar=calendar))
        dsShift = xr.concat([dsShift, dsNew], dim='Time')

    return dsShift
