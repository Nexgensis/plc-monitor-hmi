-- migrations/001_serial_settings.sql
ALTER TABLE plc_profile ADD COLUMN parity TEXT DEFAULT 'E' CHECK(parity IN ('N', 'E', 'O'));
ALTER TABLE plc_profile ADD COLUMN data_bits INTEGER DEFAULT 7 CHECK(data_bits IN (7, 8));
ALTER TABLE plc_profile ADD COLUMN stop_bits INTEGER DEFAULT 1 CHECK(stop_bits IN (1, 2));
ALTER TABLE plc_profile ADD COLUMN serial_mode TEXT DEFAULT 'ASCII' CHECK(serial_mode IN ('RTU', 'ASCII'));
