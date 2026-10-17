"""TVT N9000_LOG_TYPE from vendor dvrdvstypedef.h (2BAD/tvt mirror).

These SDK type values are NOT the raw mlogtype `action` numeric namespace.
Only explicitly named SDK types/macros are resolved through this table.
Source: https://github.com/2BAD/tvt/blob/master/docs/vendor/include/dvrdvstypedef.h
"""

SDK_TYPES = [
    ('LOG_ALARM_MOTION', 'Motion detection alarm'),
    ('LOG_ALARM_SENSOR', 'Sensor alarm'),
    ('LOG_ALARM_ALARMOUTPUT', 'Alarm output'),
    ('LOG_ALARM_OCCLUSION', 'Video occlusion alarm'),
    ('LOG_ALARM_VLOSS', 'Video loss alarm'),
    ('LOG_ALARM_VEHICLE_PLATE_MATCH', 'Vehicle plate match'),
    ('LOG_ALARM_INTELLIGENT', 'Intelligent alarm'),
    ('LOG_ALARM_FACE_MATCH', 'Face match'),
    ('LOG_ALARM_COMBINED', 'Combined alarm'),
    ('LOG_OPERATE_RECORD_SPB', 'Recording search / playback / backup'),
    ('LOG_OPERATE_MANUAL_RECORD', 'Manual recording'),
    ('LOG_OPERATE_MANUAL_ALARM', 'Manual alarm'),
    ('LOG_OPERATE_SYSTEM_MAINTENANCE', 'System maintenance'),
    ('LOG_OPERATE_PTZ_CONTROL', 'PTZ control'),
    ('LOG_OPERATE_AUDIO_TALK', 'Two-way audio'),
    ('LOG_OPERATE_SYSTEM_SCR', 'System startup / shutdown'),
    ('LOG_OPERATE_LOGIN_LOGOUT', 'Login / logout'),
    ('LOG_OPERATE_SNAPSHOT_MSPB', 'Snapshot operation'),
    ('LOG_OPERATE_FORMAT_HD', 'Disk formatting'),
    ('LOG_OPERATE_HDD_INSERT', 'Disk insertion'),
    ('LOG_OPERATE_FEATURELIBRARY', 'Feature library operation'),
    ('LOG_CONFIG_CHANNEL', 'Channel configuration'),
    ('LOG_CONFIG_RECORD', 'Recording configuration'),
    ('LOG_CONFIG_ALARM', 'Alarm configuration'),
    ('LOG_CONFIG_DISK', 'Disk configuration'),
    ('LOG_CONFIG_NETWORK', 'Network configuration'),
    ('LOG_CONFIG_SCHEDULE', 'Schedule configuration'),
    ('LOG_CONFIG_USER', 'User configuration'),
    ('LOG_CONFIG_BASIC', 'Basic configuration'),
    ('LOG_EXCEPTION_UNLAWFUL_ACCESS', 'Unlawful access'),
    ('LOG_EXCEPTION_DISK_FULL', 'Disk full'),
    ('LOG_EXCEPTION_DISK_IO_ERROR', 'Disk read/write error'),
    ('LOG_EXCEPTION_IP_COLLISION', 'IP address conflict'),
    ('LOG_EXCEPTION_INTERNET_DISCONNECT', 'Network disconnected'),
    ('LOG_EXCEPTION_IPC_DISCONNECT', 'IP camera disconnected'),
    ('LOG_EXCEPTION_ABNORMAL_SHUTDOWN', 'Abnormal shutdown'),
    ('LOG_EXCEPTION_NO_DISK', 'No disk'),
    ('LOG_EXCEPTION_VIDEO_LOSS', 'Video loss'),
]
SDK_BY_CODE = {256 + index: (macro, label) for index, (macro, label) in enumerate(SDK_TYPES)}
SDK_BY_MACRO = dict(SDK_TYPES)
# DD_LOG_INFO vendor reference: named operations are a separate SDK vocabulary.
# No numeric raw-action values are inferred from the ordering in that manual.
SDK_BY_MACRO.update({
    'DD_LOG_TYPE_USER_ADD': 'Add user',
    'DD_LOG_TYPE_USER_MODIFY': 'Modify user permissions',
    'DD_LOG_TYPE_USER_DELETE': 'Delete user',
    'DD_LOG_TYPE_CHANGE_PASSWD': 'Change password',
    'DD_LOG_TYPE_LOAD_DEFAULT': 'Restore default configuration',
    'DD_LOG_TYPE_IMPORT_CONFIG': 'Import configuration',
    'DD_LOG_TYPE_EXPORT_CONFIG': 'Export configuration',
    'DD_LOG_TYPE_PLAYBACK_PLAY': 'Start playback',
    'DD_LOG_TYPE_PLAYBACK_PAUSE': 'Pause playback',
    'DD_LOG_TYPE_PLAYBACK_RESUME': 'Resume playback',
    'DD_LOG_TYPE_PLAYBACK_FF': 'Fast-forward playback',
    'DD_LOG_TYPE_PLAYBACK_REW': 'Rewind playback',
    'DD_LOG_TYPE_PLAYBACK_STOP': 'Stop playback',
    'DD_LOG_TYPE_BACKUP_START': 'Start backup',
    'DD_LOG_TYPE_BACKUP_COMPLETE': 'Backup completed',
    'DD_LOG_TYPE_BACKUP_CANCEL': 'Backup cancelled',
    'DD_LOG_TYPE_BACKUP_FAIL': 'Backup failed',
    'DD_LOG_TYPE_CHGE_IP': 'Change network IP address',
    'DD_LOG_TYPE_CHGE_HTTP_PORT': 'Change HTTP port',
    'DD_LOG_TYPE_CHGE_SER_PORT': 'Change network server port',
    'DD_LOG_TYPE_MOTION_START': 'Motion detection started',
    'DD_LOG_TYPE_MOTION_END': 'Motion detection ended',
    'DD_LOG_TYPE_VLOSS_START': 'Video loss started',
    'DD_LOG_TYPE_VLOSS_END': 'Video loss ended',
})


def payload_fields(payload):
    return dict(part.split(':', 1) for part in payload.split(';') if ':' in part)


def describe_action(payload, action_map):
    fields = payload_fields(payload)
    action = fields.get('action', '').strip()
    macro = action if action in SDK_BY_MACRO else ''
    if macro:
        return SDK_BY_MACRO[macro], macro, 'TVT SDK named action/type macro'
    # A distinct, explicit SDK-type field is not confused with raw action IDs.
    explicit = fields.get('sdk_log_type', fields.get('n9000_type', '')).strip()
    if explicit:
        if explicit in SDK_BY_MACRO:
            macro = explicit
        else:
            try:
                macro = SDK_BY_CODE.get(int(explicit, 16 if explicit.lower().startswith('0x') else 10), ('', ''))[0]
            except ValueError:
                pass
        if macro:
            return SDK_BY_MACRO[macro], macro, 'TVT SDK explicitly identified N9000_LOG_TYPE'
    try:
        number = int(action, 16 if action.lower().startswith('0x') else 10)
    except ValueError:
        return ('Action: ' + action if action else '', '', 'Unmapped raw action; original payload retained')
    if number in action_map:
        return action_map[number], '', 'Existing raw-image action mapping'
    return f'Action ID: {number}', '', 'Unmapped raw action; SDK type namespace is separate'
