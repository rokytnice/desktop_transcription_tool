#!/bin/bash
systemctl --user restart transcription-offline.service
systemctl --user status transcription-offline.service --no-pager
