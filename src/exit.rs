use nix::sys::signal::{SigSet, SIGHUP, SIGINT, SIGQUIT, SIGTERM};

use errors::*;


/// Block exit signals from the main thread with mask inherited by children
pub fn block_exit_signals() -> Result<()> {
    let mask = create_exit_sigmask();
    mask.thread_block()
        .chain_err(|| ErrorKind::BlockExitSignals)
}

/// Trap exit signals from a signal handling thread
pub fn trap_exit_signals() -> Result<()> {
    let mask = create_exit_sigmask();

    let sig = mask.wait().chain_err(|| ErrorKind::TrapExitSignals)?;

    info!("\nReceived {:?}", sig);

    Ok(())
}

fn create_exit_sigmask() -> SigSet {
    let mut mask = SigSet::empty();

    mask.add(SIGINT);
    mask.add(SIGQUIT);
    mask.add(SIGTERM);
    mask.add(SIGHUP);

    mask
}
